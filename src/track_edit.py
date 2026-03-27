#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# Author: Chris Kuethe <chris.kuethe@gmail.com> , https://github.com/ckuethe/radiacode-tools
# SPDX-License-Identifier: MIT

from argparse import ArgumentParser, Namespace, RawDescriptionHelpFormatter
from datetime import datetime, timedelta
from math import atan2, cos, pow, radians, sin, sqrt
from textwrap import dedent
from typing import List, Tuple

import pandas as pd

from radiacode_tools.rc_files import RcTrack
from radiacode_tools.rc_types import GeoBox, GeoCircle, TimeRange, TrackPoint
from radiacode_tools.rc_utils import localtz
from radiacode_tools.rc_validators import geobox, geocircle, timerange


def get_args() -> Namespace:
    "The usual argument parsing stuff"

    longhelp: str = """
    Track Filtering
    ===============

    This program subjects all the points in a track to a series of tests to
    decide which points are retained.

    Filter criteria can be a:
    - time range, eg. "1979-03-24T04:00:00~1979-04-01T23:59:59"
    - rectangular area, eg. 33.885816,-106.742654~33.311648,-106.074214
    - radius around a point, eg. 11.5759546,165.2330638,20000

    Latitude and longitude are decimal degrees, with optional [+-] prefix:


    Filter logic
    ============
    If neither include nor exclude filters are given, the track is copied without
    changes; "you didn't tell me to make any edits, so I didn't do anything."
    
    "Include" parameters operate as an OR condition. To be eligible, a point
    must meet all of the inclusion criteria. If only include filters are given,
    selection effectively begins with a default deny, then points matching all
    of the include conditions will be included. Typical use would be selecting
    a rectangular geometry during a particular time window.

    "Exclude" parameters operate as an OR condtion. To be selected, a point must
    not match any of the exclusion criteria. If only exclude parameters are given,
    selection effectively begins with a default allow, and then points not matched
    by any of the exclude conditions will be included. Typical use may be cutting
    out a restricted area, or trimming some excess recording off the end of track.

    If both include and exclude filters are given
    """

    ap: ArgumentParser = ArgumentParser(
        description="Edit a Radiacode track by clipping to (or out) time ranges and geometries.",
        epilog=dedent(longhelp),
        formatter_class=RawDescriptionHelpFormatter,
    )
    ap.add_argument(  # -t include-time-range
        "-t",
        "--include-time-range",
        type=timerange,
        metavar="TIMERANGE",
        default=[],
        action="append",
        help="include points within the time range YYYY-mm-ddTHH:MM:SS~YYYY-mm-ddTHH:MM:SS in your local timezone",
    )
    ap.add_argument(  # -T exclude-time-range
        "-T",
        "--exclude-time-range",
        type=timerange,
        metavar="TIMERANGE",
        default=[],
        action="append",
        help="exclude points within the time range",
    )
    ap.add_argument(  # -g include-geo
        "-g",
        "--include-geo",
        default=[],
        action="append",
        metavar="GEOBOX",
        type=geobox,
        help="include points within a bounding box lat1,lon1~lat2,lon2 (decimal degrees)",
    )
    ap.add_argument(  # -G exclude-geo
        "-G",
        "--exclude-geo",
        default=[],
        metavar="GEOBOX",
        action="append",
        type=geobox,
        help="exclude points within a bounding box",
    )
    ap.add_argument(  # -g include-radius
        "-r",
        "--include-radius",
        default=[],
        action="append",
        metavar="RADIUS",
        type=geocircle,
        help="include points within some radius of a point lat,lon,radius (decimal degrees, meters)",
    )
    ap.add_argument(  # -G exclude-radius
        "-R",
        "--exclude-radius",
        default=[],
        action="append",
        metavar="RADIUS",
        type=geocircle,
        help="exclude points within some radius of a point",
    )
    ap.add_argument(  # -n track-name
        "-n",
        "--track-name",
        type=str,
        metavar="STR",
        help='set the name of the output track, default "<originalname> (edit)"',
    )
    ap.add_argument(  # -o output
        "-o",
        "--output",
        type=str,
        metavar="FILENAME",
        help="Save output to different name, default <inputfile>~",
    )
    ap.add_argument(nargs=1, dest="filename", metavar="FILE")

    rv: Namespace = ap.parse_args()
    rv.filename = rv.filename[0]
    if rv.output is None:
        rv.output = rv.filename
    return rv


def earthdistance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    See https://en.wikipedia.org/wiki/Haversine_formula for the underlying math.
    """

    y1: float = radians(lat1)
    y2: float = radians(lat2)
    x1: float = radians(lon1)
    x2: float = radians(lon2)

    d_y: float = y2 - y1
    d_x: float = x2 - x1

    # I could've used `**` instead of `pow` but I had to import from math anyway...
    a: float = pow(sin(d_y / 2), 2) + cos(y1) * cos(y2) * pow(sin(d_x / 2), 2)
    c: float = 2 * atan2(sqrt(a), sqrt(1 - a))

    return c * 6371e3  # Wikipedia says we approximate earth radius as 6371km in Haversine


def check_timerange(member: TrackPoint, container: TimeRange) -> bool:
    "start <= t < end"
    return container.dt_start <= member.dt < container.dt_end


def check_geobox(member: TrackPoint, container: GeoBox) -> bool:
    """
    Check if a point is inside a rectangle, eg.

    (x1,y1)                                               (x1,y1)
           +-----------+                     +-----------+
           |           |                     |         * |
           |   x       |         or          |           |
           |           |                     |           |
           +-----------+                     +-----------+
                        (x2,y2)       (x2,y2)

    """
    x: bool = (
        min(container.p1.longitude, container.p2.longitude)
        <= member.longitude
        <= max(container.p1.longitude, container.p2.longitude)
    )
    y: bool = (
        min(container.p1.latitude, container.p2.latitude)
        <= member.longitude
        <= max(container.p1.latitude, container.p2.latitude)
    )
    return x and y


def check_geocircle(member: TrackPoint, container: GeoCircle) -> bool:
    r"""
    Check if a point is within a circle
       ________
      /        \
     /       *  \
    |            |
    |      x---->|
    |        r   |
     \          /
      \________/

    """
    return (
        earthdistance(member.latitude, member.longitude, container.point.latitude, container.point.longitude)
        <= container.radius
    )


def check_timeranges(df: pd.DataFrame, container: List[TimeRange]) -> pd.Series:
    if not isinstance(container, list):  # pyright: ignore reportUnnecessaryIsInstance
        raise ValueError("container must be a list")
    result = pd.Series([False] * len(df), index=df.index)
    for tr in container:
        mask = (df["DateTime"] >= tr.dt_start) & (df["DateTime"] < tr.dt_end)
        result = result | mask
    return result


def check_geoboxes(df: pd.DataFrame, container: List[GeoBox]) -> pd.Series:
    if not isinstance(container, list):  # pyright: ignore reportUnnecessaryIsInstance
        raise ValueError("container must be a list")
    result = pd.Series([False] * len(df), index=df.index)
    for gb in container:
        min_lat = min(gb.p1.latitude, gb.p2.latitude)
        max_lat = max(gb.p1.latitude, gb.p2.latitude)
        min_lon = min(gb.p1.longitude, gb.p2.longitude)
        max_lon = max(gb.p1.longitude, gb.p2.longitude)
        mask = (
            (df["Latitude"] >= min_lat)
            & (df["Latitude"] <= max_lat)
            & (df["Longitude"] >= min_lon)
            & (df["Longitude"] <= max_lon)
        )
        result = result | mask
    return result


def check_geocircles(df: pd.DataFrame, container: List[GeoCircle]) -> pd.Series:
    if not isinstance(container, list):  # pyright: ignore reportUnnecessaryIsInstance
        raise ValueError("container must be a list")
    from math import asin, cos, radians, sin, sqrt

    result = pd.Series([False] * len(df), index=df.index)
    R = 6371e3
    for gc in container:
        center_lat_rad = radians(gc.point.latitude)
        center_lon_rad = radians(gc.point.longitude)
        lat_rad = radians(df["Latitude"].values)
        lon_rad = radians(df["Longitude"].values)
        d_lat = lat_rad - center_lat_rad
        d_lon = lon_rad - center_lon_rad
        a = sin(d_lat / 2) ** 2 + cos(center_lat_rad) * cos(lat_rad) * sin(d_lon / 2) ** 2
        c = 2 * asin(sqrt(a))
        distances = R * c
        mask = distances <= gc.radius
        result = result | mask
    return result


def edit_track(args: Namespace, track: RcTrack) -> Tuple[int, int]:
    """
    Filter points in an RcTrack based on include/exclude criteria for time ranges,
    rectangular areas, and circular regions.

    The filter modifies the track in place by keeping or removing points that
    match the specified criteria.

    Returns a tuple of (before_len,after_len), and modifies the input track
    """

    if args.track_name is None:
        args.track_name = f"{track.name} (edit)"
    track.name = args.track_name

    before_len: int = len(track.df)

    for include_tr in args.include_time_range:
        track.filter_by_timerange(include_tr.dt_start, include_tr.dt_end, inclusive_end=False)
    for exclude_tr in args.exclude_time_range:
        track.filter_by_timerange_inverse(exclude_tr.dt_start, exclude_tr.dt_end, inclusive_end=False)

    for include_gb in args.include_geo:
        track.filter_by_geobox(
            include_gb.p1.latitude, include_gb.p1.longitude, include_gb.p2.latitude, include_gb.p2.longitude
        )
    for exclude_gb in args.exclude_geo:
        track.filter_by_geobox_inverse(
            exclude_gb.p1.latitude, exclude_gb.p1.longitude, exclude_gb.p2.latitude, exclude_gb.p2.longitude
        )

    for include_rc in args.include_radius:
        track.filter_by_geocircle(include_rc.point.latitude, include_rc.point.longitude, include_rc.radius)
    for exclude_rc in args.exclude_radius:
        track.filter_by_geocircle_inverse(exclude_rc.point.latitude, exclude_rc.point.longitude, exclude_rc.radius)

    after_len: int = len(track.df)
    return (before_len, after_len)


def main() -> None:
    args: Namespace = get_args()

    if True:
        print("parsed args:")
        for x in dir(args):
            if x.startswith("_"):
                continue
            print(f"\t{x}: {getattr(args, x)}")
        print()

    # file deepcode ignore PT: Shut up snyk, this is a CLI utility intended to walk files...
    track: RcTrack = RcTrack()
    track.load_file(args.filename)
    edit_len: tuple[int, int] = edit_track(args, track)

    print(f"edit results: {edit_len[0]} -> {edit_len[1]} points")
    if len(track.df) > 0:
        T_start: datetime = track.df.iloc[0]["DateTime"].astimezone(localtz)
        T_end: datetime = track.df.iloc[-1]["DateTime"].astimezone(localtz)
        duration: timedelta = T_end - T_start
        print(f"track times: {T_start} -> {T_end}, duration={duration}")
    else:
        print("track times: no points remaining")

    track.write_file(args.output)


if __name__ == "__main__":
    main()
