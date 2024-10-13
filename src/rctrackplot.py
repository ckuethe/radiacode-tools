#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# Author: Chris Kuethe <chris.kuethe@gmail.com> , https://github.com/ckuethe/radiacode-tools
# SPDX-License-Identifier: MIT


import os
from argparse import ArgumentParser, Namespace
from datetime import datetime, timezone
from typing import List

import kaleido as kd  # plotly does this automatically, but this is a dependency check
import pandas as pd  # kaleido does this automatically, but this is a dependency check
import plotly.express as px

# Load the RadiaCode tools
from rcfiles import RcTrack
from rctypes import TrackPoint

# Figure out what the local timezone is, once, because I use it so often
localtz = datetime.now(timezone.utc).astimezone().tzinfo


def get_args() -> Namespace:
    "The usual argument handling stuff"

    def PositiveInt(s: str) -> int:
        rv = int(s)
        if rv > 0:
            return rv
        raise ValueError()

    def PositiveFloat(s: str) -> float:
        rv = float(s)
        if rv > 0:
            return rv
        raise ValueError()

    ap = ArgumentParser()
    ap.add_argument("-o", "--output-file", type=str, metavar="FILE", help="[<input_file>.png]")
    ap.add_argument(
        "-a",
        "--accuracy",
        type=PositiveFloat,
        default=15.0,
        help="Maximum point error in meters [%(default)s]",
    )
    ap.add_argument("-d", "--downsample", type=PositiveInt, default=16, help="[%(default)s]")
    ap.add_argument("-r", "--min-count-rate", type=PositiveFloat)
    ap.add_argument("-R", "--max-count-rate", type=PositiveFloat)
    ap.add_argument("--interactive", default=False, action="store_true", help="Open an interactive plot in a browser")
    ap.add_argument("--opacity", type=PositiveFloat, default=0.25, help="Marker opacity [%(default)s]")
    ap.add_argument(
        "--palette",
        default="turbo",
        choices=["magma", "rainbow", "thermal", "turbo", "veridis"],
        help="see https://plotly.com/python/builtin-colorscales/ [%(default)s]",
    )
    ap.add_argument("--renderer", choices=["plotly", "hvplot"], default="plotly")
    ap.add_argument(nargs=1, dest="input_file", metavar="FILE")

    rv = ap.parse_args()
    rv.input_file = os.path.expanduser(rv.input_file[0])
    if rv.output_file is None:
        rv.output_file = rv.input_file + ".png"
    return rv


def rangefinder(l, a=None):
    "What's the range of a list?"
    if a:
        return rangefinder([getattr(x, str(a)) for x in l])
    return (min(l), max(l))


def range_probe(l: List[TrackPoint]):
    "Find the range of all the fields in a list of TrackPoints"
    ranges = {"len": len(l)}
    for f in l[0]._fields:
        try:
            ranges[f] = rangefinder(l, f)
        except Exception:
            pass

    ranges.pop("comment", None)
    ranges.pop("datetime", None)
    return ranges


def downsample_trackpoints(l: List[TrackPoint], factor=4) -> List[TrackPoint]:
    "Downsample the list by averaging"
    rv = []
    samples: List[TrackPoint] = []

    def _mean(l):
        return sum(l) / len(l)

    def _sl2tp(samples):
        "Sample List to TrackPoint"
        dt = [x.datetime.timestamp() for x in samples]
        lat = [x.latitude for x in samples]
        lon = [x.longitude for x in samples]
        countrate = [x.countrate for x in samples]
        doserate = [x.doserate for x in samples]
        accuracy = [x.accuracy for x in samples]

        dt = datetime.fromtimestamp(_mean(dt), localtz)
        lat = _mean(lat)
        lon = _mean(lon)
        doserate = _mean(doserate)
        countrate = _mean(countrate)
        accuracy = _mean(accuracy)

        return TrackPoint(dt, lat, lon, accuracy, doserate, countrate)

    for i in range(0, len(l), factor):
        samples = l[i : i + factor]
        rv.append(_sl2tp(samples))

    samples = l[i:]
    rv.append(_sl2tp(samples))
    return rv


def main() -> None:
    args = get_args()
    tk = RcTrack(args.input_file)

    bounding_box = range_probe(tk.points)
    print(bounding_box)

    if args.downsample >= 2:
        tk.points = downsample_trackpoints(tk.points, args.downsample)

    # FIXME would a pandas dataframe or parquet be better? can i just
    for i in range(len(tk.points)):
        x = list(tk.points[i])
        x[0] = x[0].astimezone(localtz)
        tk.points[i] = TrackPoint(*x)

    if args.min_count_rate or args.max_count_rate:
        for i in range(len(tk.points) - 1, -1, -1):
            if (args.min_count_rate and tk.points[i].countrate < args.min_count_rate) or (
                args.max_count_rate and tk.points[i].countrate > args.max_count_rate
            ):
                tk.points.pop(i)

    for i in range(len(tk.points) - 1, -1, -1):
        if tk.points[i].accuracy > 15:
            tk.points.pop(i)

    if "plotly" == args.renderer:
        render_plotly(tk, args)
    if "hvplot" == args.renderer:
        render_hvplot(tk, args)


def render_plotly(tk: RcTrack, args: Namespace):
    fig = px.scatter_mapbox(
        tk.points,
        lat="latitude",
        lon="longitude",
        hover_name="datetime",
        zoom=14,  # FIXME compute this from bounding box
        color="doserate",
        color_continuous_scale=args.palette,
        # opacity=0.25,
        # size="countrate",
        height=900,
        width=1440,
    )
    fig.update_layout(mapbox_style="open-street-map")
    fig.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0})
    fig.write_image(args.output_file)
    if args.interactive:
        fig.show()

    # FIXME also try holoviz? this looks https://examples.holoviz.org/gallery/opensky/opensky.html


def render_hvplot(tk: RcTrack, args: Namespace):
    raise NotImplementedError


if __name__ == "__main__":
    main()
