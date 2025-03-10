#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# Author: Chris Kuethe <chris.kuethe@gmail.com> , https://github.com/ckuethe/radiacode-tools
# SPDX-License-Identifier: MIT


import os
from argparse import ArgumentParser, Namespace
from datetime import datetime, timedelta
from json import loads as jloads
from typing import Tuple

import matplotlib.pyplot as plt
import numpy as np

# Load the RadiaCode tools
from rcfiles import RcSpectrogram
from rctypes import EnergyCalibration, palettes
from rcutils import timerange


def _dt_range(s: str) -> Tuple[float, float]:
    """
    Validate a range like
    00:00:00~23:19:00
    12:34:56~
    ~12:34:56
    """
    w = s.split("~")
    a = 0.0
    b = 2.0**32
    if w[0]:
        t = [int(x, 10) for x in w[0].split(":")]
        a = timedelta(hours=t[0], minutes=t[1], seconds=t[2]).total_seconds()
    if w[1]:
        t = [int(x, 10) for x in w[1].split(":")]
        b = timedelta(hours=t[0], minutes=t[1], seconds=t[2]).total_seconds()
    return a, b


def _samp_range(s: str) -> Tuple[int, int]:
    w = s.split("~")
    a = 0
    b = 2**32
    if w[0]:
        a = int(w[0], 10)
    if w[1]:
        b = int(w[1], 10)

    return a, b


def get_args() -> Namespace:
    "The usual argument handling stuff"
    ap = ArgumentParser()
    ap.add_argument(
        "-l",
        "--linear",
        default=True,
        dest="logscale",
        action="store_false",
        help="plot the intensity on a linear scale rather than a logarithm",
    )
    ap.add_argument("-o", "--output-file", type=str, metavar="FILE", help="[<input_file>.png]")
    ap.add_argument("-s", "--serial-number", type=str, metavar="STR")
    mtx = ap.add_mutually_exclusive_group()
    mtx.add_argument(
        "--sample",
        type=str,
        dest="sample_filter",
        metavar="N~N",
        help="select spectrogram samples by sample number",
    )
    mtx.add_argument(
        "--duration",
        type=str,
        dest="duration_filter",
        metavar="H:M:S~H:M:S",
        help="select spectrogram sample by time since recording start",
    )
    mtx.add_argument(
        "--time",
        type=str,
        dest="time_filter",
        metavar="Y-M-DTh:m:s~Y-M-DTh:m:s",
        help="select spectrogram sample by absolute timestamp",
    )

    ap.add_argument(
        "--palette",
        default="turbo",
        choices=palettes,
        help="see https://plotly.com/python/builtin-colorscales/ [%(default)s]",
    )
    ap.add_argument(nargs=1, dest="input_file", metavar="FILE")

    rv = ap.parse_args()

    rv.input_file = os.path.expanduser(rv.input_file[0])
    if rv.output_file is None:
        rv.output_file = rv.input_file + ".png"

    if False:
        pass
    elif rv.duration_filter:
        try:
            rv.duration_filter = _dt_range(rv.duration_filter)
        except Exception:
            print(f"Unable to parse relative time range: {rv.duration_filter}")
            exit(1)
    elif rv.time_filter:
        try:
            tmp = timerange(rv.time_filter)
            rv.time_filter = tmp[0].timestamp(), tmp[1].timestamp()
        except Exception:
            print(f"Unable to parse timestamp range: {rv.time_filter}")
            exit(1)
    elif rv.sample_filter:
        try:
            rv.sample_filter = _samp_range(rv.sample_filter)
        except Exception:
            print(f"Unable to parse sample number range: {rv.sample_filter}")
            exit(1)
    return rv


def plot_spectrogram(
    sg: RcSpectrogram,
    args: Namespace,
    plot_size=(24, 8),
) -> None:
    "Given a spectrogram and the CLI args, produce the spectrogram"
    plt.figure(figsize=plot_size)
    plt.margins(x=0, y=0.01)
    plt.grid(True, which="both", ls="-")
    plt.xticks(range(0, sg.channels + 1, 16), rotation=45)
    plt.xlabel("Channel")
    plt.ylabel("Time")
    plt.title(sg.name)

    def array_extend(a, l):
        return a + [0] * (l - len(a))

    data = np.array([array_extend(s.counts, sg.channels) for s in sg.samples])
    ylabels = np.array([s.datetime for s in sg.samples])
    xlabels = range(sg.channels + 1)
    cmap = plt.colormaps[args.palette]  # jet, turbo, plasma, inferno, viridis
    if args.logscale:
        # can't take the logarithm of a non-positive real number, so we add 1 to every
        # bin which then makes every input have a valid output. You wouldn't do that
        # for a numerical analysis, but this is just to make the plot work nicely.
        plt.pcolormesh(data + np.ones_like(data), cmap=cmap, norm="log")
    else:
        plt.pcolormesh(data, cmap=cmap)

    if args.output_file != "/dev/null":
        plt.savefig(args.output_file)
        print(f"saved image in {args.output_file}")
    plt.show()


def main() -> None:
    args = get_args()
    spg = RcSpectrogram()
    if args.input_file.endswith(".rcspg"):
        spg.load_file(args.input_file)
    elif args.input_file.endswith(".ndjson"):
        with open(args.input_file) as ifd:
            sn = None or args.serial_number
            records = [jloads(l) for l in ifd if "counts" in l]

        if sn is None:
            sn = records[0]["serial_number"]
            print(f"Assuming serial number {sn}")
        spg.add_calibration(EnergyCalibration(*records[0]["calibration"]))
        spg.serial_number = sn

        # Filter serial number
        records = [x for x in records if x["serial_number"] == sn]
        # Assume the timestamp of this spectrogram is the time the first record was saved
        spg.timestamp = datetime.fromtimestamp(records[0]["timestamp"])

        # Selecting a subset of samples
        if args.sample_filter:
            records = records[args.sample_filter[0] : args.sample_filter[1]]
        if args.time_filter:
            records = [x for x in records if args.time_filter[0] <= x["timestamp"] <= args.time_filter[1]]
        if args.duration_filter:
            records = [
                x
                for x in records
                if args.duration_filter[0] <= (x["timestamp"] - records[0]["timestamp"]) <= args.duration_filter[1]
            ]

        # spg.name = "iad ct scan"
        _ = [spg.add_point(timestamp=p["timestamp"], counts=p["counts"]) for p in records]

    else:
        print(f"Not sure how to handle {args.input_file}")
        return

    plot_spectrogram(spg, args)


if __name__ == "__main__":
    main()
