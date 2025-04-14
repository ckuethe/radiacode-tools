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
from os.path import basename, dirname
from os.path import join as pathjoin
from os.path import realpath
from typing import Any, Dict, Iterable

from radiacode_tools.rc_files import RcTrack
from radiacode_tools.rc_utils import DATEFMT_TZ, parse_datetime


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
        help="Display name of Track [Track <date>]",
    )
    ap.add_argument(
        "-k",
        "--comment",
        type=str,
        metavar="STR",
        default="",
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
            rv.output = pathjoin(dirname(rv.input), f"{basename(rv.input)}.rcspg")

    return rv


def load_file_lines(args) -> Dict[str, Dict[str, Any]]:
    with open(args.input) as ifd:
        db: Dict[str, Dict[str, Any]] = {}
        timekey = ""
        for line in ifd:
            rec: Dict[str, Any] = json.loads(line)
            # Pick up the first serial number we see
            if args.serial_number is None and "serial_number" in rec:
                args.serial_number = rec["serial_number"]
                print(f"Set serial number to {args.serial_number}")

            if "calibration" in rec:  # spectrum, not relevant for tracks
                continue

            if args.serial_number and "serial_number" in rec and rec["serial_number"] != args.serial_number:
                continue

            # Horology note: it is the time it is, until it isn't. If your clock only shows
            # hours and minutes, then 09:15:00.001 is the same time as 09:15:59.999. By the
            # same reasoning, we drop the fractional seconds, and just assume that any data
            # arriving during one particular second belongs to that second... thus the
            # fromtimestamp(int(x)) or .replace('.000Z', 'Z')

            if "gnss" in rec:
                if rec["gnss"] is False:  # no useful data, skip it
                    continue
                rec["datetime"] = parse_datetime(rec["time"].replace(".000Z", "Z"), DATEFMT_TZ)
                timekey = str(rec["datetime"])
                db[timekey] = rec
                continue
            else:
                # FIXME - this reveals the need to include host time in all the messages, in case there is clock drift
                rec["rctime"] = rec.pop("time")
                _ = {k: rec.pop(k) for k in list(rec.keys()) if rec[k] is None}  # strip null/empty/None values

                if timekey:
                    db[timekey].update(rec)

        return db


def keys_missing(required: Iterable, have: Iterable) -> bool:
    missing = set(required).difference(set(have))
    return True if missing else False


def convert_lines_to_track(args: Namespace, lines: Dict[str, Dict[str, Any]]) -> RcTrack:
    trk = RcTrack()
    req_keys = {"datetime", "lat", "lon", "dose_rate", "epc", "count_rate"}

    for ts in sorted(lines.keys()):
        d = lines[ts]
        if keys_missing(req_keys, d.keys()):
            continue

        trk.add_point(
            dt=d["datetime"],
            latitude=d["lat"],
            longitude=d["lon"],
            accuracy=d["epc"],
            dose_rate=d["dose_rate"],
            count_rate=d["count_rate"],
        )

    if args.name:
        trk.name = args.name
    trk.serialnumber = args.serial_number
    trk.comment = args.comment
    trk.flags = "EC"
    return trk


def main() -> None:
    args = get_args()
    db = load_file_lines(args)
    trk = convert_lines_to_track(args, db)
    print(f"Created track with {len(trk.points)} points")
    trk.write_file(args.output)


if __name__ == "__main__":
    main()
