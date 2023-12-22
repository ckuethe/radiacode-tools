#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

from uuid import uuid4, UUID
from textwrap import dedent
import xmltodict
from argparse import ArgumentParser, Namespace
from rcutils import stringify
import os
from io import TextIOWrapper
from typing import List, Dict, Any

__version__ = "0.0.9"
__creator__ = "https://github.com/ckuethe/radiacode-tools"


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

    if check and (2 != rv["calibration_order"]):
        raise ValueError("invalid calibration order")

    if check and (len(rv["calibration_values"]) != rv["calibration_order"] + 1):
        raise ValueError("Inconsistent calibration polynomial")

    return rv


def load_radiacode_spectrum(filename: str = None, fileobj: TextIOWrapper = None) -> Dict[str, Any]:
    if filename and fileobj:
        raise ValueError("Only one of filename or fileobj may be given")
    if filename:
        ifd = open(filename)
    elif fileobj:
        ifd = fileobj
    else:
        raise ValueError("One of filename or fileobj are required")

    try:
        sp = xmltodict.parse(ifd.read(), dict_constructor=dict)["ResultDataFile"]["ResultDataList"]["ResultData"]
    except Exception:  # something went wrong
        if filename:  # don't leak the fd
            ifd.close()
        raise  # let the caller figure out what to do next

    if filename:
        ifd.close()

    fg = sp["EnergySpectrum"]  # let this raise if the spectrum is missing. No foreground = not useful
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


def get_rate_from_spectrum(filename: str) -> float:
    s = load_radiacode_spectrum(filename)
    return sum(s["foreground"]["spectrum"]) / s["foreground"]["duration"]


def squareformat(a: List[Any], columns: int = 16):
    "reformat the a long list of numbers (any elements, actually) as some nice lines"
    if columns < 1:
        raise ValueError("Columns must be greater than zero")
    rv = []
    for x in range(columns):
        line = " ".join([f"{i:5}" for i in a[x * columns : (x + 1) * columns]])
        rv.append(line)
    return "\n".join(rv)


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

        timestamp = spectrum["start_time"]
        if isinstance(timestamp, list):
            timestamp = timestamp[time_index]

        rv = f"""
        <RadMeasurement id="rm-{tag}">
            <Remark>Title: {spectrum[layer]['name']}</Remark>
            <MeasurementClassCode>{mclass}</MeasurementClassCode>
            <StartDateTime>{timestamp}</StartDateTime>
            <RealTimeDuration>PT{spectrum[layer]["duration"]}S</RealTimeDuration>
            <Spectrum id="rm-{tag}-sp" radDetectorInformationReference="radiacode-csi-sipm" energyCalibrationReference="ec-{tag}"> 
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
    "Hard-coded information about the RC-101 and RC-102, id is fixed to 'radiacode-csi-sipm'"
    # Category and Kind are from N42, Description is free text
    rv = """
    <RadDetectorInformation id="radiacode-csi-sipm">
        <RadDetectorCategoryCode>Gamma</RadDetectorCategoryCode>
        <RadDetectorKindCode>CsI</RadDetectorKindCode>
        <RadDetectorDescription>CsI:Tl scintillator, coupled to SiPM</RadDetectorDescription>
        <RadDetectorLengthValue units="mm">10</RadDetectorLengthValue>
        <RadDetectorWidthValue units="mm">10</RadDetectorWidthValue>
        <RadDetectorDepthValue units="mm">10</RadDetectorDepthValue>
        <RadDetectorVolumeValue units="cc">1</RadDetectorVolumeValue>
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
            <RadInstrumentComponentVersion>1.42.00</RadInstrumentComponentVersion>
        </RadInstrumentVersion>
        <RadInstrumentVersion>
            <RadInstrumentComponentName>Converter</RadInstrumentComponentName>
            <RadInstrumentComponentVersion>{__version__}</RadInstrumentComponentVersion>
        </RadInstrumentVersion>
    </RadInstrumentInformation>
    """
    return dedent(rv).strip()


def format_output(
    uuid="",
    instrument_info="",
    detector_info="",
    fg_cal="",
    fg_spectrum="",
    bg_cal="",
    bg_spectrum="",
    fwhm_cal="",
) -> str:
    if uuid is None:
        uuid = uuid4()
    template = f"""
    <?xml version="1.0"?>
    <?xml-model href="http://physics.nist.gov/N42/2011/schematron/n42.sch" type="application/xml" schematypens="http://purl.oclc.org/dsdl/schematron"?>
    <RadInstrumentData xmlns="http://physics.nist.gov/N42/2011/N42" 
                   xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" 
                   xsi:schemaLocation="http://physics.nist.gov/N42/2011/N42 http://physics.nist.gov/N42/2011/n42.xsd" 
                   n42DocUUID="{uuid}">

    <!-- What created this file? -->
    <RadInstrumentDataCreatorName>{__creator__}</RadInstrumentDataCreatorName>

    <!-- What product was used to gather the data? -->
    {instrument_info}

    <!-- What detection technology is used? -->
    {detector_info}

    <!-- Calibration factors, mapping channel/bin to energy level. Foreground and background may have separate calibrations-->
    {fg_cal}
    {bg_cal}
    {fwhm_cal}

    <!-- Primary spectrum in this file-->
    {fg_spectrum}

    <!-- N42 can transport multiple spectra; If present, this will be used as background -->
    {bg_spectrum}

    <!-- All done! -->
    </RadInstrumentData>
    """
    return dedent(template).strip()


def get_args() -> Namespace:
    ap = ArgumentParser()

    def _uuid(s):
        if s.strip():
            return UUID(s)
        return None

    ap.add_argument(
        "-i",
        "--input",
        type=str,
        metavar="NAME",
        required=True,
        help="primary source data file",
    )
    ap.add_argument(
        "-b",
        "--background",
        type=str,
        metavar="NAME",
        help="Retrieve background from this file, using the background series if it exists or the main series otherwise.",
    )
    mtx = ap.add_mutually_exclusive_group()
    mtx.add_argument(
        "-o",
        "--output",
        type=str,
        metavar="NAME",
        help="[<foreground>.n42]",
    )
    mtx.add_argument(
        "-r",
        "--recursive",
        default=False,
        action="store_true",
        help="if given, treat the input path as a directory to process recursively with autogenerated output names",
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


def process_single_fileobj(fileobj: TextIOWrapper) -> str:
    """
    wrapper to allow conversion from a file object

    this is used by the conversion server
    """
    fg_data = load_radiacode_spectrum(fileobj=fileobj)

    n42data = format_output(
        uuid=None,
        instrument_info=make_instrument_info(fg_data),
        detector_info=make_detector_info(),
        fg_cal=format_calibration(fg_data),
        bg_cal=format_calibration(fg_data, fg=False),
        fg_spectrum=format_spectrum(fg_data),
        bg_spectrum=format_spectrum(fg_data, fg=False),
    )

    return n42data


def process_single_file(fg_file=None, bg_file=None, out_file=None, uuid=None, overwrite=False) -> None:
    "Read a data file and convert it"
    if out_file and os.path.exists(out_file) and overwrite is False:
        return  # shortcut for recursive mode

    fg_data = load_radiacode_spectrum(filename=fg_file)
    if bg_file:
        bg_data = load_radiacode_spectrum(filename=bg_file)
    else:
        bg_data = fg_data

    n42data = format_output(
        uuid=uuid,
        instrument_info=make_instrument_info(fg_data),
        detector_info=make_detector_info(),
        fg_cal=format_calibration(fg_data),
        bg_cal=format_calibration(bg_data, fg=False),
        fg_spectrum=format_spectrum(fg_data),
        bg_spectrum=format_spectrum(bg_data, fg=False),
    )

    if out_file is None:
        out_file = f"{fg_file}.n42"

    mode = "w" if overwrite else "x"
    with open(out_file, mode) as ofd:
        print(f"Output file: {out_file}")
        ofd.write(dedent(n42data))


def main() -> None:
    args = get_args()

    if args.recursive:
        for cur_dir, _, files in os.walk(args.input):
            for fn in files:
                if fn.endswith(".xml"):
                    src_file = os.path.join(cur_dir, fn)
                    process_single_file(fg_file=src_file, out_file=f"{src_file}.n42")
    else:
        process_single_file(
            fg_file=args.input,
            bg_file=args.background,
            out_file=args.output,
            uuid=args.uuid,
            overwrite=args.overwrite,
        )


if __name__ == "__main__":
    main()
