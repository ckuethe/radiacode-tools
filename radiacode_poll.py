#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import n42convert
import importlib.metadata
import warnings
from argparse import ArgumentParser, Namespace
from dateutil.parser import parse as dp
from datetime import timedelta, datetime
from radiacode import RadiaCode, Spectrum
from tempfile import mkstemp
from textwrap import dedent
from time import sleep
from tqdm.auto import tqdm
from typing import Dict
from uuid import uuid4
import sys
import os
import re


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
        + "between the initial spectrum and the final spectrum. The start time will be the"
        + "time the intial spectrum was captured. If not specified, the output file will"
        + "contain the intial and final spectra, which can be subtracted in other tools.",
    )
    ap.add_argument(
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

    return rv


def get_device_id(dev: RadiaCode) -> Dict[str, str]:
    "Poll the device for all its identifiers"
    rv = {
        "fw": dev.fw_signature(),
        "fv": dev.fw_version(),
        "hw_num": dev.hw_serial_number(),
        "sernum": dev.serial_number(),
    }
    try:
        f = re.search(
            'Signature: (?P<fw_signature>[0-9A-F]{8}), FileName="(?P<fw_file>.+?)", IdString="(?P<product>.+?)"',
            rv["fw"],
        ).groupdict()
        rv.update(f)
        rv.pop("fw")
    except (AttributeError, TypeError):
        pass

    try:
        f = re.search(
            "Boot version: (?P<boot_ver>[0-9.]+) (?P<boot_date>[A-Z].+?:\d{2}) [|] Target version: (?P<fw_ver>[0-9.]+) (?P<fw_date>[A-Z].+?:\d{2})",
            rv["fv"],
        ).groupdict()
        rv.update(f)
        rv.pop("fv")
    except (AttributeError, TypeError):
        pass
    return rv


def make_instrument_info(dev_id: Dict[str, str]):
    "Create the N42 RadInstrumentInformation element"
    try:
        radiacode_ver = importlib.metadata.version("radiacode")
    except importlib.metadata.PackageNotFoundError:
        radiacode_ver = "Unknown"

    rv = f"""
    <RadInstrumentInformation id="rii-{dev_id["hw_num"]}">
        <RadInstrumentManufacturerName>Radiacode</RadInstrumentManufacturerName>
        <RadInstrumentIdentifier>{dev_id["sernum"]}</RadInstrumentIdentifier>
        <RadInstrumentModelName>{dev_id["model"]}</RadInstrumentModelName>
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


def format_spectrum(hw_num: str, res: Spectrum, bg: bool = False):
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
        <EnergyCalibration id="ec-{hw_num}">
            <CoefficientValues> {res.a0} {res.a1} {res.a2} </CoefficientValues>
        </EnergyCalibration>
        """

    spec_str = f"""
        <RadMeasurement id="rm-{hw_num}-{tag}">
            <MeasurementClassCode>{mc}</MeasurementClassCode>
            <StartDateTime> {sdt} </StartDateTime>
            <RealTimeDuration> PT{md}S </RealTimeDuration>
            <Spectrum id="sp-{hw_num}-{tag}" radDetectorInformationReference="radiacode-csi-sipm" energyCalibrationReference="ec-{hw_num}"> 
                <LiveTimeDuration> PT{md}S </LiveTimeDuration>
                <ChannelData compressionCode="None"> {count_str} </ChannelData> 
            </Spectrum>
        </RadMeasurement>
        """
    return dedent(cal_str), dedent(spec_str)


def spec_dose(s: Spectrum) -> float:
    "Given a Spectrum, return an estimate of the total absorbed dose in uSv"
    # According to the Health Physics Society:
    #     Radiation absorbed dose and effective dose in the international system
    #     of units (SI system) for radiation measurement uses "gray" (Gy) and
    #     "sievert" (Sv), respectively.
    #     [...]
    #     For practical purposes with gamma and x rays, these units of measure
    #     for exposure or dose are considered equal.
    # via https://hps.org/publicinformation/ate/faqs/radiationdoses.html

    kev2j = 1.60218e-16
    mass = 4.51e-3  # kg, CsI:Tl density is 4.51g/cm^3, crystal is 1cm^3
    a0, a1, a2 = s.a0, s.a1, s.a2

    def _ce(c):
        return a0 + a1 * c + a2 * c**2

    keVz = sum([_ce(ch) * n for ch, n in enumerate(s.counts)])
    gray = keVz * kev2j / mass
    uSv = gray * 1e6
    return uSv


def main() -> None:
    args = get_args()
    dev = RadiaCode(args.btaddr)
    if args.reset_spectrum:
        dev.spectrum_reset()
    if args.reset_dose:
        dev.dose_reset()

    dev_id = get_device_id(dev)
    measurement = dev.spectrum()  # Always grab a spectrum to start

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
            e0 = spec_dose(measurement)
            with tqdm(
                desc=f"Target Dose ({args.accumulate_dose:.3f}uSv)",
                unit="uSv",
                total=round(args.accumulate_dose, 3),
            ) as t:
                try:
                    waiting = True
                    while waiting:
                        sleep(1)
                        recv_dose = spec_dose(dev.spectrum()) - e0
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
            dm = Spectrum(
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

    ofd = sys.stdout
    if args.outfile:
        tfd, tfn = mkstemp(dir=".")
        os.close(tfd)
        ofd = open(tfn, "w")

    print(data, file=ofd)

    if args.outfile:
        ofd.close()
        os.rename(tfn, args.outfile)


if __name__ == "__main__":
    main()
