#!/usr/bin/env python3

import n42convert
import importlib.metadata
from argparse import ArgumentParser, Namespace
from dateutil.parser import parse as dp
from datetime import timedelta
from radiacode import RadiaCode, Spectrum
from tempfile import mkstemp
from textwrap import dedent
from time import strftime, sleep
from tqdm.auto import tqdm
from typing import Dict
from uuid import uuid4
import sys
import os


def get_args() -> Namespace:
    ap = ArgumentParser(description="Poll a RadiaCode PSRD and produce an N42 file")
    ap.add_argument(
        "-b",
        "--btaddr",
        type=str,
        metavar="MAC",
        help="Bluetooth address of device; leave blank to use USB",
    )
    ap.add_argument(
        "--accumulate",
        default=False,
        action="store_true",
        help="Measure until interrupted with ^C",
    )
    ap.add_argument(
        "--accumulate-time",
        type=str,
        metavar="TIME",
        help="Measure for a given amount of time (timedelta)",
    )
    ap.add_argument(
        "--accumulate-dose",
        type=str,
        metavar="DOSE",
        help="Measure until a certain dose has been accumulated (uSv)",
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
        help="Reset accumulated spectrum. Very Dangerous.",
    )
    ap.add_argument(dest="outfile", nargs="?", default="", help="default: stdout")
    return ap.parse_args()


def get_device_id(dev: RadiaCode) -> Dict[str, str]:
    "Poll the device for all its identifiers"
    rv = {
        "model": dev.fw_signature().split("=")[-1].replace('"', ""),
        "fw_ver": dev.fw_version().split(" | ")[1].split()[2],
        "hw_num": dev.hw_serial_number(),
        "sernum": dev.serial_number(),
    }
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


def format_spectrum(hw_num: str, res: Spectrum):
    "format a radiacode.Spectrum to be printed by n42convert"
    md = int(res.duration.total_seconds())
    sdt = strftime("%Y-%m-%dT%H:%M:%S")
    counts = " ".join([str(i) for i in res.counts])

    cal_str = f"""
        <EnergyCalibration id="ec-{hw_num}">
            <CoefficientValues> {res.a0} {res.a1} {res.a2} </CoefficientValues>
        </EnergyCalibration>
        """

    spec_str = f"""
        <RadMeasurement id="rm-{hw_num}">
            <MeasurementClassCode>Foreground</MeasurementClassCode>
            <StartDateTime> {sdt} </StartDateTime>
            <RealTimeDuration> PT{md}S </RealTimeDuration>
            <Spectrum id="rm-{hw_num}-fg" radDetectorInformationReference="radiacode-csi-sipm" energyCalibrationReference="ec-{hw_num}"> 
                <LiveTimeDuration> PT{md}S </LiveTimeDuration>
                <ChannelData compressionCode="None"> {counts} </ChannelData> 
            </Spectrum>
        </RadMeasurement>
        """
    return dedent(cal_str), dedent(spec_str)


def main() -> None:
    args = get_args()
    dev = RadiaCode(args.btaddr)
    if args.reset_spectrum:
        dev.spectrum_reset()
    if args.reset_dose:
        dev.dose_reset()

    dev_id = get_device_id(dev)
    measurement = dev.spectrum()  # Always grab a spectrum to start

    if args.accumulate or args.accumulate_time or args.accumulate_dose:  # are we accumulating measurements over time?
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
        elif args.accumulate_dose:
            raise NotImplementedError("Sorry, haven't done this yet")

        # Cool, we've waited long enough, grab the end spectrum
        m1 = dev.spectrum()

        # Subtract initial measurement to get just the integrated data
        dt = m1.duration - measurement.duration
        dc = [x[1] - x[0] for x in zip(measurement.counts, m1.counts)]
        measurement = Spectrum(
            duration=dt,
            a0=m1.a0,
            a1=m1.a1,
            a2=m1.a2,
            counts=dc,
        )

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
