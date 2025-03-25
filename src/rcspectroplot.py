#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# Author: Chris Kuethe <chris.kuethe@gmail.com> , https://github.com/ckuethe/radiacode-tools
# SPDX-License-Identifier: MIT


import os
from argparse import ArgumentParser, Namespace
from datetime import datetime
from json import loads as jloads

import matplotlib.pyplot as plt
import numpy as np

# Load the RadiaCode tools
from radiacode_tools.rc_files import RcSpectrogram
from radiacode_tools.rc_types import EnergyCalibration, palettes
from radiacode_tools.rc_validators import _duration_range, _samp_range, _timerange


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
        type=_samp_range,
        dest="sample_filter",
        metavar="N~N",
        help="select spectrogram samples by sample number",
    )
    mtx.add_argument(
        "--duration",
        type=_duration_range,
        dest="duration_filter",
        metavar="H:M:S~H:M:S",
        help="select spectrogram sample by time since recording start",
    )
    mtx.add_argument(
        "--time",
        type=_timerange,
        dest="time_filter",
        metavar="Y-M-DTh:m:s~Y-M-DTh:m:s",
        help="select spectrogram sample by absolute timestamp",
    )
    ap.add_argument("--plot-nonblocking", default=True, action="store_false", dest="blocking")

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

    # if True:
    #     pass
    # elif rv.duration_filter:
    #     try:
    #         rv.duration_filter = _duration_range(rv.duration_filter)
    #     except Exception:
    #         print(f"Unable to parse relative time range: {rv.duration_filter}")
    #         exit(1)
    # elif rv.time_filter:
    #     try:
    #         tmp = _timerange(rv.time_filter)
    #         rv.time_filter = tmp[0].timestamp(), tmp[1].timestamp()
    #     except Exception:
    #         print(f"Unable to parse timestamp range: {rv.time_filter}")
    #         exit(1)
    # elif rv.sample_filter:
    #     try:
    #         rv.sample_filter = _samp_range(rv.sample_filter)
    #     except Exception:
    #         print(f"Unable to parse sample number range: {rv.sample_filter}")
    #         exit(1)
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

    plt.show(block=args.blocking)


def load_spectrogram_from_ndjson(args: Namespace) -> RcSpectrogram:
    """
    The newline delimited JSON produced by rcmultlog takes a bit of processing
    to turn it into an RcSpectrogram, for example filtering for a selected device
    serial number, but after that it's just like the regular radiacode format.
    """
    spg = RcSpectrogram()
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
    if len(records) == 0:
        print("No data after filtering")
        exit()
    # Assume the timestamp of this spectrogram is the time the first record was saved
    spg.timestamp = datetime.fromtimestamp(records[0]["timestamp"])
    _ = [spg.add_point(timestamp=p["timestamp"], counts=p["counts"]) for p in records]

    return spg


def filter_spectrogram(args: Namespace, spg: RcSpectrogram) -> None:
    "it may be desirable to select just a subset of points. spectrogram is edited in place"
    if args.sample_filter:
        spg.samples = spg.samples[args.sample_filter[0] : args.sample_filter[1] + 1]
    if args.time_filter:
        spg.samples = [x for x in spg.samples if (args.time_filter.t_start <= x.datetime <= args.time_filter.t_end)]
    if args.duration_filter:
        t0 = spg.samples[0].datetime
        spg.samples = [
            x
            for x in spg.samples
            if (args.duration_filter[0] <= (x.datetime - t0).total_seconds() <= args.duration_filter[1])
        ]


def main() -> None:
    args = get_args()
    if args.input_file.endswith(".rcspg"):
        spg = RcSpectrogram()
        spg.load_file(args.input_file)
    elif args.input_file.endswith(".ndjson"):
        spg = load_spectrogram_from_ndjson(args)
    else:
        print(f"Not sure how to handle {args.input_file}")
        return

    filter_spectrogram(args, spg)

    plot_spectrogram(spg, args)


if __name__ == "__main__":
    main()
