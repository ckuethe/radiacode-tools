#!/usr/bin/env python3

import matplotlib.pyplot as plt
from uuid import uuid4, UUID
from socket import gethostname
from textwrap import dedent
import xmltodict
import xml.etree.ElementTree as ET
import xmlschema
import requests
from argparse import ArgumentParser, Namespace


def parse_spectrum(spectrum, check: bool = True):
    """Given an spectrum dict, return useful items"""
    rv = {
        "name": spectrum["SpectrumName"],
        "device_serial_number": spectrum.get("SerialNumber", None),
        "calibration_order": int(spectrum["EnergyCalibration"]["PolynomialOrder"]),
        "calibration_values": [float(f) for f in spectrum["EnergyCalibration"]["Coefficients"]["Coefficient"]],
        "duration": int(spectrum["MeasurementTime"]),
        "channels": int(spectrum["NumberOfChannels"]),
        "spectrum": [int(i) for i in spectrum["Spectrum"]["DataPoint"]],
    }

    if check and (len(rv["spectrum"]) != rv["channels"]):
        raise ValueError("spectrum length != number of channels")

    if check and (len(rv["calibration_values"]) != rv["calibration_order"] + 1):
        raise ValueError("Inconsistent calibration polynomial")

    return rv


def load_radiacode_spectrum(fn):
    with open(fn) as ifd:
        sp = xmltodict.parse(ifd.read(), dict_constructor=dict)["ResultDataFile"]["ResultDataList"]["ResultData"]

    fg = sp.get("EnergySpectrum")
    fg = parse_spectrum(fg)
    try:
        bg = sp.get("BackgroundEnergySpectrum")
        bg = parse_spectrum(bg)
    except (KeyError, AttributeError, TypeError):
        bg = None

    rv = {
        "device_name": sp["DeviceConfigReference"]["Name"],
        "start_time": sp["StartTime"],
        "end_time": sp["EndTime"],
        "foreground": fg,
        "background": bg,
    }

    return rv


def squareformat(a, columns=16):
    "reformat the a long list of numbers as some nice lines"
    rv = []
    for x in range(columns):
        line = " ".join([f"{i:5}" for i in a[x * columns : (x + 1) * columns]])
        rv.append(line)
    return "\n".join(rv)


def stringify(a):
    return " ".join([f"{x}" for x in a])


def format_calibration(spectrum, fg=True):
    "Format calibration factors from data file"
    try:
        tag = "fg" if fg else "bg"
        layer = spectrum["foreground"] if fg else spectrum["background"]
        rv = f"""
        <EnergyCalibration id="ec-{tag}">
            <CoefficientValues>{stringify(layer["calibration_values"])} </CoefficientValues>
        </EnergyCalibration>
        """
        return dedent(rv).strip()
    except (KeyError, TypeError):
        print("No background data present")
        # Spectrum file may not contain a background series. That is not an error. Other exceptions are
        return ""


def format_spectrum(spectrum, fg=True):
    try:
        tag, mclass = ("fg", "Foreground") if fg else ("bg", "Background")
        layer = mclass.lower()
        time_index = 0 if fg else 1

        rv = f"""
        <RadMeasurement id="rm-{tag}">
            <Remark>{spectrum[layer]['name']}</Remark>
            <MeasurementClassCode>{mclass}</MeasurementClassCode>
            <StartDateTime>{spectrum["start_time"][time_index]}</StartDateTime>
            <RealTimeDuration>PT{spectrum[layer]["duration"]}S</RealTimeDuration>
            <Spectrum id="rm-{tag}-sp" radDetectorInformationReference="rdi-1" energyCalibrationReference="ec-{tag}"> 
                <LiveTimeDuration>PT{spectrum[layer]["duration"]}S</LiveTimeDuration>
                <ChannelData compressionCode="None">
                    {stringify(spectrum[layer]["spectrum"])}
                </ChannelData> 
            </Spectrum>
        </RadMeasurement>
        """
        return dedent(rv).strip()
    except Exception:
        return ""


def make_detector_info():
    "Hard-coded information about the RC-101 and RC-102"
    # Category and Kind are from N42, Description is free text
    rv = """
    <RadDetectorInformation id="rdi-1">
        <RadDetectorCategoryCode>Gamma</RadDetectorCategoryCode>
        <RadDetectorKindCode>CsI</RadDetectorKindCode>
        <RadDetectorDescription>CsI:Tl scintillator, coupled to SiPM</RadDetectorDescription>
    </RadDetectorInformation>
    """
    return dedent(rv).strip()


def make_instrument_info(data):
    try:
        # Extract the serial number from the data file
        serial_number = data.get("foreground", data.get("background"))["device_serial_number"]
        serial_number = f"<RadInstrumentIdentifier>{serial_number}</RadInstrumentIdentifier>"
    except KeyError:
        serial_number = ""

    rv = f"""
    <RadInstrumentInformation id="rii-1">
        <RadInstrumentManufacturerName>Radiacode</RadInstrumentManufacturerName>
        {serial_number}
        <RadInstrumentModelName>{data["device_name"]}</RadInstrumentModelName>
        <RadInstrumentClassCode>Spectroscopic Personal Radiation Detector</RadInstrumentClassCode>
      
        <!-- I have a feature request to include firmware and app version in the exported xml files. -->
        <RadInstrumentVersion>
            <RadInstrumentComponentName>Firmware</RadInstrumentComponentName>
            <RadInstrumentComponentVersion>4.06</RadInstrumentComponentVersion>
        </RadInstrumentVersion>
        <RadInstrumentVersion>
            <RadInstrumentComponentName>App</RadInstrumentComponentName>
            <RadInstrumentComponentVersion>1.41.00</RadInstrumentComponentVersion>
        </RadInstrumentVersion>
        <RadInstrumentVersion>
            <RadInstrumentComponentName>Converter</RadInstrumentComponentName>
            <RadInstrumentComponentVersion>0.0.2</RadInstrumentComponentVersion>
        </RadInstrumentVersion>
    </RadInstrumentInformation>
    """
    return dedent(rv).strip()


def format_output(**kwargs) -> str:
    template = """
    <?xml version="1.0"?>
    <?xml-model href="http://physics.nist.gov/N42/2011/schematron/n42.sch" type="application/xml" schematypens="http://purl.oclc.org/dsdl/schematron"?>
    <RadInstrumentData xmlns="http://physics.nist.gov/N42/2011/N42" 
                   xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" 
                   xsi:schemaLocation="http://physics.nist.gov/N42/2011/N42 http://physics.nist.gov/N42/2011/n42.xsd" 
                   n42DocUUID="{uuid}">

    <!-- What created this file? -->
    <RadInstrumentDataCreatorName>https://github.com/ckuethe/radiacode-tools</RadInstrumentDataCreatorName>

    <!-- What product was used to gather the data? -->
    {instrument_info}

    <!-- What detection technology is used? -->
    {detector_info}

    <!-- Calibration factors, mapping channel/bin to energy level. Foreground and background may have separate calibrations-->
    {fg_cal}
    {bg_cal}

    <!-- Primary spectrum in this file-->
    {fg_spectrum}

    <!-- N42 can transport multiple spectra; If present, this will be used as background -->
    {bg_spectrum}

    <!-- All done! -->
    </RadInstrumentData>
    """
    return dedent(template).format(**kwargs).strip()


def get_args() -> Namespace:
    ap = ArgumentParser()

    def _uuid(s):
        if s.strip():
            return UUID(s)
        return None

    ap.add_argument(
        "-f",
        "--foreground",
        type=str,
        metavar="FILE",
        required=True,
        help="primary source data file",
    )
    ap.add_argument(
        "-b",
        "--background",
        type=str,
        metavar="FILE",
        help="Retrieve background from this file, using the background series if it exists or the main series otherwise.",
    )
    ap.add_argument(
        "-o",
        "--output",
        type=str,
        metavar="FILE",
        help="[<foreground>.n42]",
    )
    ap.add_argument(
        "--overwrite",
        default=False,
        action="store_true",
        help="allow existing file to be overwritten",
    )
    ap.add_argument(
        "-u",
        "--uuid",
        metavar="UUID",
        type=_uuid,
        help="specify a UUID for the generated document. [<random>]",
    )
    return ap.parse_args()


def main() -> None:
    args = get_args()

    fg_data = load_radiacode_spectrum(args.foreground)
    if args.background:
        bg_data = load_radiacode_spectrum(args.background)
    else:
        bg_data = fg_data

    if args.output is None:
        args.output = f"{args.foreground}.n42"
        print(f"Output file: {args.output}")

    if args.uuid is None:
        args.uuid = uuid4()

    n42data = format_output(
        uuid=args.uuid,
        instrument_info=make_instrument_info(fg_data),
        detector_info=make_detector_info(),
        fwhm_cal="",
        fg_cal=format_calibration(fg_data),
        bg_cal=format_calibration(bg_data, fg=False),
        fg_spectrum=format_spectrum(fg_data),
        bg_spectrum=format_spectrum(bg_data, fg=False),
    )

    mode = "w" if args.overwrite else "x"
    with open(args.output, mode) as ofd:
        ofd.write(dedent(n42data))


if __name__ == "__main__":
    main()
