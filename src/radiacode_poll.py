#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# Author: Chris Kuethe <chris.kuethe@gmail.com> , https://github.com/ckuethe/radiacode-tools
# SPDX-License-Identifier: MIT

import os
import sys
import warnings
from argparse import ArgumentParser, Namespace, _MutuallyExclusiveGroup
from datetime import datetime, timedelta
from tempfile import mkstemp
from time import sleep
from urllib.parse import quote_plus
from zlib import compress as deflate

import radiacode  # type: ignore
from dateutil.parser import parse as dp  # type: ignore
from tqdm.auto import tqdm  # type: ignore

from radiacode_tools.rc_files import RcN42, RcSpectrum
from radiacode_tools.rc_types import EnergyCalibration, RcHwInfo, SpectrumLayer
from radiacode_tools.rc_utils import (
    get_device_id,
    get_dose_from_spectrum,
    probe_radiacode_devices,
)
from radiacode_tools.rc_validators import _positive_float


def get_args() -> Namespace:
    ap: ArgumentParser = ArgumentParser(description="Poll a RadiaCode PSRD and produce an N42 file")
    dmx: _MutuallyExclusiveGroup = ap.add_mutually_exclusive_group()
    dmx.add_argument(
        "-b",
        "--btaddr",
        type=str,
        metavar="MAC",
        help="Bluetooth address of device; leave blank to use USB",
    )
    dmx.add_argument(
        "-s",
        "--serial-number",
        type=str,
        metavar="STR",
        help="Serial number of USB connected device",
    )
    ap.add_argument(
        "-l",
        "--list-devices",
        default=False,
        action="store_true",
        help="List connected devices and exit",
    )
    mx: _MutuallyExclusiveGroup = ap.add_mutually_exclusive_group()  # only one way of accumulation may be selected
    mx.add_argument(
        "--accumulate",
        default=False,
        action="store_true",
        help="Measure until interrupted with ^C",
    )
    mx.add_argument(
        "--accumulate-time",
        type=str,
        metavar="TIME",
        help="Measure for a given amount of time (timedelta)",
    )
    mx.add_argument(
        "--accumulate-dose",
        type=_positive_float,
        metavar="DOSE",
        help="Measure until a certain dose has been accumulated (uSv)",
    )
    ap.add_argument(
        "-B",
        "--bgsub",
        default=False,
        action="store_true",
        help="Produce a single spectrum measurement file containing only the difference "
        + "between the initial spectrum and the final spectrum. The start time will be the "
        + "time the intial spectrum was captured. If not specified, the output file will "
        + "contain the intial and final spectra, which can be subtracted in other tools.",
    )
    ux: _MutuallyExclusiveGroup = ap.add_mutually_exclusive_group()
    ux.add_argument(
        "-u",
        "--url",
        default=False,
        action="store_true",
        help="Generate a RADDATA url. See Sandia Report SAND2023-10003 for more details",
    )
    ux.add_argument(
        "-q",
        "--qrcode",
        default=False,
        action="store_true",
        help="Generate a RADDATA QR code. See Sandia Report SAND2023-10003 for more details",
    )
    ap.add_argument(
        "--reset-spectrum",
        default=False,
        action="store_true",
        help="Reset accumulated spectrum. Dangerous.",
    )
    ap.add_argument(
        "--reset-dose",
        default=False,
        action="store_true",
        help="Reset accumulated dose. Very Dangerous.",
    )
    ap.add_argument(dest="outfile", nargs="?", default="", help="default: stdout")
    rv: Namespace = ap.parse_args()

    # post-processing stages.
    rv.want_accumulation = any([rv.accumulate, rv.accumulate_time, rv.accumulate_dose])
    if rv.qrcode:
        rv.bgsub = True

    return rv


def wait_for_keyboard_interrupt() -> None:
    with tqdm(desc="Integration time", unit="s", total=float("inf")) as t:
        try:
            while True:
                sleep(1)
                t.update()
        except KeyboardInterrupt:
            t.close()


def wait_for_time(args: Namespace) -> None:
    tx = dp(args.accumulate_time).time()
    tx = int(timedelta(hours=tx.hour, minutes=tx.minute, seconds=tx.second).total_seconds())

    with tqdm(desc="Integration time", unit="s", total=tx) as t:
        try:
            for _ in range(tx):
                sleep(1)
                t.update()
        except KeyboardInterrupt:
            t.close()


def wait_for_dose(args: Namespace, m0: radiacode.Spectrum, dev: radiacode.RadiaCode) -> float:
    initial_energy: float = get_dose_from_spectrum(m0.counts, EnergyCalibration(a0=m0.a0, a1=m0.a1, a2=m0.a2))
    recv_dose = 0.0
    with tqdm(
        desc=f"Target Dose ({args.accumulate_dose:.3f}uSv)",
        unit="uSv",
        total=round(args.accumulate_dose, 3),
    ) as t:
        try:
            waiting = True
            while waiting:
                sleep(1)
                s: radiacode.Spectrum = dev.spectrum()
                recv_dose = (
                    get_dose_from_spectrum(s.counts, EnergyCalibration(a0=s.a0, a1=s.a1, a2=s.a2)) - initial_energy
                )
                t.n = round(recv_dose, 3)
                t.display()
                if recv_dose >= args.accumulate_dose:
                    waiting = False
        except KeyboardInterrupt:
            t.close()
    return recv_dose


def main() -> None:
    args: Namespace = get_args()

    if args.list_devices:
        probe_radiacode_devices()
        return

    if args.btaddr:
        dev: radiacode.RadiaCode = radiacode.RadiaCode(bluetooth_mac=args.btaddr)
    else:
        dev = radiacode.RadiaCode(serial_number=args.serial_number)

    if args.reset_spectrum:
        dev.spectrum_reset()
    if args.reset_dose:
        dev.dose_reset()

    dev_id: RcHwInfo = get_device_id(dev)
    measurement: radiacode.Spectrum = dev.spectrum()  # Always grab a spectrum to start
    obs_start: datetime = datetime.utcnow()
    n42_writer: RcN42 = RcN42()
    sp: RcSpectrum = RcSpectrum()
    if args.want_accumulation:  # are we accumulating measurements over time?
        # suppress tqdm warnings when we exceed the expected maximum
        warnings.filterwarnings("ignore", module="tqdm")
        if args.accumulate:
            wait_for_keyboard_interrupt()
        elif args.accumulate_time:  # yep, for a fixed duration
            wait_for_time(args)
        elif args.accumulate_dose:  # yep, until a set dose is reached
            wait_for_dose(args, measurement, dev)
        # Cool, we've waited long enough, grab the end spectrum
        measurement1: radiacode.Spectrum = dev.spectrum()

        if args.bgsub:  # Subtract initial measurement to get just the accumulated data
            dt: timedelta = measurement1.duration - measurement.duration
            diff_counts: list[int] = [x[1] - x[0] for x in zip(measurement.counts, measurement1.counts)]
            sp.fg_spectrum = SpectrumLayer(
                device_model=dev_id.model,
                serial_number=dev_id.serial_number,
                calibration=EnergyCalibration(a0=measurement.a0, a1=measurement.a1, a2=measurement.a2),
                timestamp=obs_start,
                duration=dt,
                channels=len(diff_counts),
                counts=diff_counts,
                spectrum_name="untitled",
            )
        else:  # don't subtract the background, just include it.
            sp.bg_spectrum = SpectrumLayer(
                device_model=dev_id.model,
                serial_number=dev_id.serial_number,
                calibration=EnergyCalibration(a0=measurement.a0, a1=measurement.a1, a2=measurement.a2),
                timestamp=obs_start,
                duration=measurement.duration,
                channels=len(measurement.counts),
                counts=measurement.counts,
                spectrum_name="untitled background",
            )
            sp.fg_spectrum = SpectrumLayer(
                device_model=dev_id.model,
                serial_number=dev_id.serial_number,
                calibration=EnergyCalibration(a0=measurement1.a0, a1=measurement1.a1, a2=measurement1.a2),
                timestamp=obs_start,
                duration=measurement1.duration,
                channels=len(measurement1.counts),
                counts=measurement1.counts,
                spectrum_name="untitled foreground",
            )
        n42_writer.from_rcspectrum(sp)
        data: str = n42_writer.generate_xml()

    else:  # instantaneous capture
        sp.fg_spectrum = SpectrumLayer(
            device_model=dev_id.model,
            serial_number=dev_id.serial_number,
            calibration=EnergyCalibration(a0=measurement.a0, a1=measurement.a1, a2=measurement.a2),
            timestamp=obs_start,
            duration=measurement.duration,
            channels=len(measurement.counts),
            counts=measurement.counts,
            spectrum_name="untitled foreground",
        )
        n42_writer.from_rcspectrum(sp)
        data = n42_writer.generate_xml()

    dose: float = get_dose_from_spectrum(
        measurement.counts, EnergyCalibration(a0=measurement.a0, a1=measurement.a1, a2=measurement.a2)
    )
    print(f"Total dose: {dose:.2f}uSv ({dev_id.serial_number})", file=sys.stderr)
    ofd = None
    if args.outfile:
        tfd, tfn = mkstemp(dir=".")
        os.close(tfd)

    if args.url or args.qrcode:
        # defer import until it's needed
        from radiacode_tools import rc_radqr  # type: ignore

        enc_opts = rc_radqr.OPT_CSV_SPECTRUM
        enc_opts, msg = rc_radqr.make_qr_payload(
            lr_times=[measurement.duration.total_seconds()] * 2,
            spectrum=measurement.counts,
            calibration=[measurement.a0, measurement.a1, measurement.a2],
            detector_model=f"{dev_id.model} {dev_id.serial_number}",
            mclass="F",
            timestamp=obs_start,
            options=enc_opts,
        )
        qbody: str = quote_plus(rc_radqr.b45_encode(deflate(msg)))
        url: str = f"RADDATA://G0/{enc_opts:02X}00/{qbody}"
        if args.qrcode:
            # defer import until it's needed
            from qrcode import QRCode

            qc: QRCode = QRCode()
            qc.add_data(url)
            if args.outfile:
                ofd = open(tfn, "wb")
            qc.make_image().save(ofd)
        else:
            if args.outfile:
                ofd = open(tfn, "w")
            print(url, file=ofd)  # type: ignore

    else:
        if args.outfile:
            ofd = open(tfn, "w")
        print(data, file=ofd)  # type: ignore

    if args.outfile:
        if ofd:
            ofd.close()
        # file deepcode ignore PT: CLI tool intentionally opening the files the user asked for
        os.rename(tfn, args.outfile)


if __name__ == "__main__":
    main()
