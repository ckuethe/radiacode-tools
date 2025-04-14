#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# Author: Chris Kuethe <chris.kuethe@gmail.com> , https://github.com/ckuethe/radiacode-tools
# SPDX-License-Identifier: MIT


import os
from argparse import ArgumentParser, Namespace
from datetime import datetime
from math import log10, sqrt
from typing import Any, Dict, List

import plotly.express

# Load the RadiaCode tools
from radiacode_tools.rc_files import RcTrack
from radiacode_tools.rc_types import Number, TrackPoint, palettes
from radiacode_tools.rc_utils import localtz
from radiacode_tools.rc_validators import (
    _geometry,
    _non_negative_int,
    _positive_float,
    _rcsn,
)


def get_args() -> Namespace:
    "The usual argument handling stuff"

    ap = ArgumentParser()
    ap.add_argument("-o", "--output-file", type=str, metavar="FILE", help="[<input_file>.png]")
    ap.add_argument(
        "-a",
        "--accuracy",
        type=_positive_float,
        default=15.0,
        help="Maximum point error in meters [%(default)s]",
    )
    ap.add_argument(
        "-d", "--downsample", type=_non_negative_int, default=16, help="0 or 1 means no downsampling, [%(default)s]"
    )
    ap.add_argument("-r", "--min-count-rate", type=_positive_float)
    ap.add_argument("-R", "--max-count-rate", type=_positive_float)
    ap.add_argument("-g", "--geometry", type=_geometry, default="1600x1024", help="Image size [%(default)s]")
    ap.add_argument("-s", "--serial-number", dest="sn", type=_rcsn, metavar="STR")
    ap.add_argument("--interactive", default=False, action="store_true", help="Open an interactive plot in a browser")
    ap.add_argument("--opacity", type=_positive_float, default=0.25, help="Marker opacity [%(default)s]")
    ap.add_argument(
        "--palette",
        default="turbo",
        choices=[palettes],
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


def mean(l: List[Number]) -> float:
    return sum(l) / len(l)


def _dcf(dc) -> List[str]:
    "dataclass fields. There's gotta be a better way..."
    return list(dc.__dict__.keys())


def tracklist_range_probe(l: List[TrackPoint]):
    "Find the range of all the fields in a list of TrackPoints"
    ranges = {"len": len(l)}
    for f in _dcf(l[0]):
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

    def _sl2tp(samples):
        "Sample List to TrackPoint"
        dt = [x.dt.timestamp() for x in samples]
        lat = [x.latitude for x in samples]
        lon = [x.longitude for x in samples]
        countrate = [x.countrate for x in samples]
        doserate = [x.doserate for x in samples]
        accuracy = [x.accuracy for x in samples]

        dt = datetime.fromtimestamp(mean(dt), localtz)
        lat = mean(lat)
        lon = mean(lon)
        doserate = mean(doserate)
        countrate = mean(countrate)
        accuracy = mean(accuracy)

        return TrackPoint(dt=dt, latitude=lat, longitude=lon, accuracy=accuracy, doserate=doserate, countrate=countrate)

    for i in range(0, len(l) + 1, factor):
        samples = l[i : i + factor]
        if samples:
            rv.append(_sl2tp(samples))

    return rv


def map_ctr(bbx: Dict[str, Any]) -> Dict[str, float]:
    "Normally I'd use a GeoPoint for this, but scatter_mapbox wants a dict"
    return {
        "lat": sum(bbx["latitude"]) / 2,
        "lon": sum(bbx["longitude"]) / 2,
    }


def osm_zoom(bbx: Dict[str, Any]) -> int:
    "Estimate the OpenStreetMap zoom level from the bounding box of the track"
    # https://wiki.openstreetmap.org/wiki/Zoom_levels
    # experimentally derived coefficients that work well for me. Plug them into
    # the "y = mx+b" equation of a line and you get a pretty good conversion from
    # the diagonal size of the bounding box in decimal degrees to zoom level.
    m = -3.0
    b = 9.6
    dx = bbx["longitude"][1] - bbx["longitude"][0]
    dy = bbx["latitude"][1] - bbx["latitude"][0]
    x = log10(sqrt(dx**2 + dy**2))
    return round(m * x + b)


def _infer_plot_format_from_fn(fn: str) -> str | None:
    allowed = ["jpg", "jpeg", "png", "svg", "webp", "pdf"]
    ext = fn.lower()
    i = ext.rfind(".")
    if i >= 0:
        ext = ext[i + 1 :]
        if ext in allowed:
            return ext
    return "png"


def render_plotly(tk: RcTrack, args: Namespace, bbx: Dict[str, Any]):
    zoom = osm_zoom(bbx)
    fig = plotly.express.scatter_map(
        tk.points,
        lat="latitude",
        lon="longitude",
        hover_name="dt",
        zoom=zoom,
        center=map_ctr(bbx),
        color="doserate",
        color_continuous_scale=args.palette,
        # opacity=0.25,
        # size="countrate",
        width=args.geometry[0],
        height=args.geometry[1],
    )
    fig.update_layout(map_style="open-street-map")
    fig.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0})

    fig.write_image(args.output_file, format=_infer_plot_format_from_fn(args.output_file))
    if args.interactive:
        fig.show()


def render_hvplot(tk: RcTrack, args: Namespace, bbx: Dict[str, Any]):
    # https://hvplot.holoviz.org/user_guide/Geographic_Data.html
    # https://hvplot.holoviz.org/getting_started/installation.html
    # https://examples.holoviz.org/gallery/opensky/opensky.html
    # https://examples.holoviz.org/gallery/osm/index.html
    #
    raise NotImplementedError


def main() -> None:
    args = get_args()
    tk = RcTrack(args.input_file)

    if args.downsample >= 2:
        tk.points = downsample_trackpoints(tk.points, args.downsample)

    # FIXME would a pandas dataframe or parquet be better? would their filters be faster?
    for i in range(len(tk.points)):
        tk.points[1].dt = tk.points[i].dt.replace(tzinfo=localtz)

    if args.min_count_rate or args.max_count_rate:
        for i in range(len(tk.points) - 1, -1, -1):
            if (args.min_count_rate and tk.points[i].countrate < args.min_count_rate) or (
                args.max_count_rate and tk.points[i].countrate > args.max_count_rate
            ):
                tk.points.pop(i)

    for i in range(len(tk.points) - 1, -1, -1):
        if tk.points[i].accuracy > 15:
            tk.points.pop(i)

    bounding_box = tracklist_range_probe(tk.points)

    if "plotly" == args.renderer:
        render_plotly(tk, args, bounding_box)
    if "hvplot" == args.renderer:
        render_hvplot(tk, args, bounding_box)


if __name__ == "__main__":
    main()
