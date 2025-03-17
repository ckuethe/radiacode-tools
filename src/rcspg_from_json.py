#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# Author: Chris Kuethe <chris.kuethe@gmail.com> , https://github.com/ckuethe/radiacode-tools
# SPDX-License-Identifier: MIT

"""
Converting the raw data from rcmultilog into
spectrograms that the radiacode app might use
"""

import json
from argparse import ArgumentParser, Namespace
from datetime import datetime, timedelta
from os.path import basename, dirname
from os.path import join as pathjoin
from os.path import realpath

from radiacode_tools.rc_files import RcSpectrogram
from radiacode_tools.rc_types import EnergyCalibration


def get_args() -> Namespace:
    "The usual argparse stuff"

    ap = ArgumentParser(description="Convert json log format into radiacode formats")
    ap.add_argument(
        "-i",
        "--input",
        type=str,
        metavar="FILENAME",
        help="Input filename [/dev/stdin]",
    )
    ap.add_argument(
        "-o",
        "--output",
        type=str,
        metavar="FILENAME",
        help="Output filename: [/dev/stdout]",
    )
    ap.add_argument("-p", "--prefix", type=str, metavar="STR", default="spectrogram_", help="[%(default)s]")
    ap.add_argument(
        "-s",
        "--serial-number",
        type=str,
        metavar="STR",
        help="Select a given device from a multi-device trace [autodetected]",
    )
    ap.add_argument(
        "-n",
        "--name",
        type=str,
        metavar="STR",
        help="Display name of spectrogram [Spectrogram <date>]",
    )
    ap.add_argument(
        "-k",
        "--comment",
        type=str,
        metavar="STR",
        help="Display comment",
    )

    _dev_stdin = "/dev/stdin"
    _dev_stdout = "/dev/stdout"
    rv = ap.parse_args()
    if rv.input in ["-", "", None]:
        rv.input = _dev_stdin

    if rv.output == "-":
        rv.output = _dev_stdout
    elif rv.output in [None, ""]:
        if rv.input == _dev_stdin:
            rv.output = _dev_stdout
        else:
            rv.input = realpath(rv.input)
            rv.output = pathjoin(dirname(rv.input), f"{rv.prefix}{basename(rv.input)}.rcspg")

    return rv


def main() -> None:
    args = get_args()
    with open(args.input) as ifd:
        spg = RcSpectrogram()
        for line in ifd:
            if "counts" not in line:
                continue  # not a spectrum; might be GNSS, battery, etc. Skip it.
            if args.serial_number and args.serial_number not in line:
                continue  # not the serial number we want. Skip it

            rec = json.loads(line)
            if spg.serial_number:  # set by the first valid record
                spg.add_point(timestamp=rec["timestamp"], counts=rec["counts"])  # also updates accumulation time
            else:
                spg.timestamp = datetime.fromtimestamp(rec["timestamp"])
                spg.serial_number = args.serial_number = rec["serial_number"]  # cache the first serial number found
                spg.name = args.name or f"Spectrogram {spg.timestamp}"
                spg.comment = args.comment or ""
                spg.calibration = EnergyCalibration(*rec["calibration"])
                spg.add_point(
                    timestamp=rec["timestamp"],
                    counts=rec["counts"],
                    duration=timedelta(seconds=rec["duration"]),
                )

        spg.write_file(args.output)


if __name__ == "__main__":
    main()
