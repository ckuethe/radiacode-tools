#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# Author: Chris Kuethe <chris.kuethe@gmail.com> , https://github.com/ckuethe/radiacode-tools
# SPDX-License-Identifier: MIT

import importlib.metadata
import os
import sys
import warnings
from argparse import ArgumentParser, Namespace
from datetime import datetime, timedelta
from tempfile import mkstemp
from textwrap import dedent
from time import sleep
from typing import Dict
from urllib.parse import quote_plus
from uuid import uuid4
from zlib import compress as deflate

import radiacode
from dateutil.parser import parse as dp
from tqdm.auto import tqdm

import n42convert
from rcutils import get_device_id, get_dose_from_spectrum, probe_radiacode_devices


def get_args() -> Namespace:
    def posfloat(s):
        f = float(s)
        if f > 0:
            return f
        raise ValueError("value must be greater than 0")

    ap = ArgumentParser(description="Poll a RadiaCode PSRD and produce an N42 file")
    ap.add_argument(
        "-b",
        "--btaddr",
        type=str,
        metavar="MAC",
        help="Bluetooth address of device; leave blank to use USB",
    )
    ap.add_argument(
        "-l",
        "--list-devices",
        default=False,
        action="store_true",
        help="List connected devices and exit",
    )
    mx = ap.add_mutually_exclusive_group()  # only one way of accumulation may be selected
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
        type=posfloat,
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
    ux = ap.add_mutually_exclusive_group()
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
    rv = ap.parse_args()

    # post-processing stages.
    rv.a = any([rv.accumulate, rv.accumulate_time, rv.accumulate_dose])
    if rv.qrcode:
        rv.bgsub = True

    return rv


def make_instrument_info(dev_id: Dict[str, str]):
    "Create the N42 RadInstrumentInformation element"
    radiacode_ver = importlib.metadata.version("radiacode")

    rv = f"""
    <RadInstrumentInformation id="rii-{dev_id["hw_num"]}">
        <RadInstrumentManufacturerName>Radiacode</RadInstrumentManufacturerName>
        <RadInstrumentIdentifier>{dev_id["sernum"]}</RadInstrumentIdentifier>
        <RadInstrumentModelName>{dev_id["product"]}</RadInstrumentModelName>
        <RadInstrumentClassCode>Spectroscopic Personal Radiation Detector</RadInstrumentClassCode>
      
        <RadInstrumentVersion>
            <RadInstrumentComponentName>Firmware</RadInstrumentComponentName>
            <RadInstrumentComponentVersion>{dev_id["fw_ver"]}</RadInstrumentComponentVersion>
        </RadInstrumentVersion>
        <RadInstrumentVersion>
            <RadInstrumentComponentName>python-radiacode</RadInstrumentComponentName>
            <RadInstrumentComponentVersion>{radiacode_ver}</RadInstrumentComponentVersion>
        </RadInstrumentVersion>
        <RadInstrumentVersion>
            <RadInstrumentComponentName>Converter</RadInstrumentComponentName>
            <RadInstrumentComponentVersion>{n42convert.__version__}</RadInstrumentComponentVersion>
        </RadInstrumentVersion>
    </RadInstrumentInformation>
    """
    return dedent(rv).strip()


def format_spectrum(hw_num: str, res: radiacode.Spectrum, bg: bool = False):
    "format a radiacode.Spectrum to be printed by n42convert"
    md = res.duration.total_seconds()
    count_str = " ".join([str(i) for i in res.counts])

    now = datetime.utcnow()
    sdt = (now - res.duration).strftime("%Y-%m-%dT%H:%M:%S")
    if bg:
        mc = "Background"
        tag = "bg"
    else:
        mc = "Foreground"
        tag = "fg"

    # This calibration is shared between the foreground and background measurements since
    # they come from the same instrument, and in this case the same observing session.

    cal_str = f"""
        <EnergyCalibration id="ec-{hw_num}-{tag}">
            <CoefficientValues> {res.a0} {res.a1} {res.a2} </CoefficientValues>
        </EnergyCalibration>
        """

    spec_str = f"""
        <RadMeasurement id="rm-{hw_num}-{tag}">
            <MeasurementClassCode>{mc}</MeasurementClassCode>
            <StartDateTime> {sdt} </StartDateTime>
            <RealTimeDuration> PT{md}S </RealTimeDuration>
            <Spectrum id="sp-{hw_num}-{tag}" radDetectorInformationReference="radiacode-csi-sipm" energyCalibrationReference="ec-{hw_num}-{tag}"> 
                <LiveTimeDuration> PT{md}S </LiveTimeDuration>
                <ChannelData compressionCode="None"> {count_str} </ChannelData> 
            </Spectrum>
        </RadMeasurement>
        """
    return dedent(cal_str), dedent(spec_str)


def main() -> None:
    args = get_args()

    if args.list_devices:
        probe_radiacode_devices()
        return

    dev = radiacode.RadiaCode(args.btaddr)
    if args.reset_spectrum:
        dev.spectrum_reset()
    if args.reset_dose:
        dev.dose_reset()

    dev_id = get_device_id(dev)
    measurement = dev.spectrum()  # Always grab a spectrum to start
    obs_start = datetime.utcnow()
    if args.a:  # are we accumulating measurements over time?
        # suppress tqdm warnings when we exceed the expected maximum
        warnings.filterwarnings("ignore", module="tqdm")
        if args.accumulate:  # yep, until ^C
            with tqdm(desc="Integration time", unit="s", total=float("inf")) as t:
                try:
                    while True:
                        sleep(1)
                        t.update()
                except KeyboardInterrupt:
                    t.close()
        elif args.accumulate_time:  # yep, for a fixed duration
            tx = dp(args.accumulate_time).time()
            tx = int(timedelta(hours=tx.hour, minutes=tx.minute, seconds=tx.second).total_seconds())

            with tqdm(desc="Integration time", unit="s", total=tx) as t:
                try:
                    for _ in range(tx):
                        sleep(1)
                        t.update()
                except KeyboardInterrupt:
                    t.close()
        elif args.accumulate_dose:  # yep, until a set dose is reached
            e0 = get_dose_from_spectrum(measurement.counts, measurement.a0, measurement.a1, measurement.a2)
            with tqdm(
                desc=f"Target Dose ({args.accumulate_dose:.3f}uSv)",
                unit="uSv",
                total=round(args.accumulate_dose, 3),
            ) as t:
                try:
                    waiting = True
                    while waiting:
                        sleep(1)
                        s = dev.spectrum()
                        recv_dose = get_dose_from_spectrum(s.counts, s.a0, s.a1, s.a2) - e0
                        t.n = round(recv_dose, 3)
                        t.display()
                        if recv_dose >= args.accumulate_dose:
                            waiting = False
                except KeyboardInterrupt:
                    t.close()

        # Cool, we've waited long enough, grab the end spectrum
        measurement1 = dev.spectrum()

        if args.bgsub:
            # Subtract initial measurement to get just the accumulated data
            dt = measurement1.duration - measurement.duration
            dc = [x[1] - x[0] for x in zip(measurement.counts, measurement1.counts)]
            dm = radiacode.Spectrum(
                duration=dt,
                a0=measurement1.a0,
                a1=measurement1.a1,
                a2=measurement1.a2,
                counts=dc,
            )
            diff_cal, diff_spec = format_spectrum(dev_id["hw_num"], dm)

        if args.bgsub:
            data = n42convert.format_output(
                detector_info=n42convert.make_detector_info(),
                instrument_info=make_instrument_info(dev_id),
                fg_cal=diff_cal,
                fg_spectrum=diff_spec,
                uuid=uuid4(),
            )
        else:
            cal, spec = format_spectrum(dev_id["hw_num"], measurement1)
            bg_cal, bg_spec = format_spectrum(dev_id["hw_num"], measurement, bg=True)
            data = n42convert.format_output(
                detector_info=n42convert.make_detector_info(),
                instrument_info=make_instrument_info(dev_id),
                fg_cal=cal,
                fg_spectrum=spec,
                bg_cal=bg_cal,  # FIXME - reuse the foreground calibration
                bg_spectrum=bg_spec,
                uuid=uuid4(),
            )
    else:  # instantaneous capture
        cal, spec = format_spectrum(dev_id["hw_num"], measurement)
        data = n42convert.format_output(
            detector_info=n42convert.make_detector_info(),
            instrument_info=make_instrument_info(dev_id),
            fg_cal=cal,
            fg_spectrum=spec,
            uuid=uuid4(),
        )

    dose = get_dose_from_spectrum(measurement.counts, measurement.a0, measurement.a1, measurement.a2)
    print(f"Total dose: {dose:.2f}uSv ({dev_id['sernum']})", file=sys.stderr)
    ofd = None
    if args.outfile:
        tfd, tfn = mkstemp(dir=".")
        os.close(tfd)

    if args.url or args.qrcode:
        import radqr

        enc_opts = radqr.OPT_CSV_SPECTRUM
        enc_opts, msg = radqr.make_qr_payload(
            lr_times=[measurement.duration.total_seconds()] * 2,
            spectrum=measurement.counts,
            calibration=[measurement.a0, measurement.a1, measurement.a2],
            detector_model=f"{dev_id['product']} {dev_id['sernum']}",
            mclass="F",
            timestamp=obs_start,
            options=enc_opts,
        )
        qbody = quote_plus(radqr.b45_encode(deflate(msg)))
        url = f"RADDATA://G0/{enc_opts:02X}00/{qbody}"
        if args.qrcode:
            import qrcode

            qc = qrcode.QRCode()
            qc.add_data(url)
            if args.outfile:
                ofd = open(tfn, "wb")
            qc.make_image().save(ofd)
        else:
            if args.outfile:
                ofd = open(tfn, "w")
            print(url, file=ofd)

    else:
        if args.outfile:
            ofd = open(tfn, "w")
        print(data, file=ofd)

    if args.outfile:
        if ofd:
            ofd.close()
        # file deepcode ignore PT: CLI tool intentionally opening the files the user asked for
        os.rename(tfn, args.outfile)


if __name__ == "__main__":
    main()
