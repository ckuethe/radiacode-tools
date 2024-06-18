#!/usr/bin/env python3
import os
import re
from argparse import ArgumentParser, Namespace
from collections import namedtuple
from datetime import datetime, timezone
from math import atan2, cos, pow, radians, sin, sqrt
from tempfile import mkstemp
from textwrap import dedent
from typing import List, NoReturn, Tuple

from rcfiles import RcTrack
from rctypes import TrackPoint

_nan = float("nan")
TimeRange = namedtuple("TimeRange", ["t_start", "t_end"], defaults=[None] * 2)
GeoBox = namedtuple("GeoBox", ["lat1", "lon1", "lat2", "lon2"], defaults=[_nan] * 4)
GeoCircle = namedtuple("GeoCircle", ["latitude", "longintude", "radius"], defaults=[_nan] * 3)
localtz = datetime.now(timezone.utc).astimezone().tzinfo


def long_help() -> NoReturn:
    txt: str = """
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

    print(dedent(txt))
    exit()


def get_args() -> Namespace:
    "The usual argument parsing stuff"

    def _timerange(s) -> TimeRange:
        "helper to validate a timerange (a pair of datetimes)"
        _datestr: str = "%Y-%m-%dT%H:%M:%S"
        w = s.split("~")
        if len(w) != 2:
            raise ValueError
        return TimeRange(
            datetime.strptime(w[0], _datestr).replace(tzinfo=localtz),
            datetime.strptime(w[1], _datestr).replace(tzinfo=localtz),
        )

    def _geobox(s) -> GeoBox:
        "helper to validate a box geometry"
        points = s.split("~")
        p0 = [float(f) for f in points[0].split(",")]
        p1 = [float(f) for f in points[1].split(",")]

        if (
            True  # just for the formatting
            and (2 == len(points))
            and (-90 <= p0[0] <= 90)
            and (-90 <= p1[0] <= 90)
            and (-180 <= p0[1] <= 180)
            and (-180 <= p1[1] <= 180)
        ):
            return GeoBox(*p0, *p1)
        raise ValueError

    def _geocircle(s) -> GeoCircle:
        try:
            rv = [float(f) for f in s.split(",")]
            if (
                True
                and (3 == len(rv))
                and (-90 <= rv[0] <= 90)
                and (-180 <= rv[1] <= 180)
                and (0 < rv[2] <= 40030e3)  # 3.1416 * 2 * 6371km
            ):
                return GeoCircle(*rv)
        except Exception:
            pass
        finally:
            raise ValueError

    ap = ArgumentParser(description="Edit a Radiacode track by clipping to (or out) time ranges and geometries.")
    ap.add_argument(  # -t include-time-range
        "-t",
        "--include-time-range",
        type=_timerange,
        metavar="TIMERANGE",
        default=[],
        action="append",
        help="include points within the time range YYYY-mm-ddTHH:MM:SS~YYYY-mm-ddTHH:MM:SS in your local timezone",
    )
    ap.add_argument(  # -T exclude-time-range
        "-T",
        "--exclude-time-range",
        type=_timerange,
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
        type=_geobox,
        help="include points within a bounding box lat1,lon1~lat2,lon2 (decimal degrees)",
    )
    ap.add_argument(  # -G exclude-geo
        "-G",
        "--exclude-geo",
        default=[],
        metavar="GEOBOX",
        action="append",
        type=_geobox,
        help="exclude points within a bounding box",
    )
    ap.add_argument(  # -g include-radius
        "-r",
        "--include-radius",
        default=[],
        action="append",
        metavar="RADIUS",
        type=_geocircle,
        help="include points within some radius of a point lat,lon,radius (decimal degrees, meters)",
    )
    ap.add_argument(  # -G exclude-radius
        "-R",
        "--exclude-radius",
        default=[],
        action="append",
        metavar="RADIUS",
        type=_geocircle,
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
    ap.add_argument("-H", "--long-help", default=False, action="store_true")
    ap.add_argument(nargs=1, dest="filename", metavar="FILE")

    rv = ap.parse_args()
    rv.filename = rv.filename[0]
    if rv.output is None:
        rv.output = rv.filename
    return rv


def earthdistance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    See https://en.wikipedia.org/wiki/Haversine_formula for the underlying math.
    """

    y1 = radians(lat1)
    y2 = radians(lat2)
    x1 = radians(lon1)
    x2 = radians(lon2)

    d_y = y2 - y1
    d_x = x2 - x1

    # I could've used `**` instead of `pow` but I had to import from math anyway...
    a = pow(sin(d_y / 2), 2) + cos(y1) * cos(y2) * pow(sin(d_x / 2), 2)
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return c * 6371e3  # Wikipedia says we approximate earth radius as 6371km in Haversine


def check_timerange(member: TrackPoint, container: TimeRange) -> bool:
    "start <= t < end"
    return container.t_start <= member.datetime < container.t_end


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
    x = min(container.lon1, container.lon2) <= member.longitude <= max(container.lon1, container.lon2)
    y = min(container.lat1, container.lat2) <= member.latitude <= max(container.lat1, container.lat2)
    return x and y


def check_geocircle(member: TrackPoint, container: GeoCircle) -> bool:
    return (
        earthdistance(member.latitude, member.longitude, container.latitude, container.longintude) <= container.radius
    )


def check_timeranges(member: TrackPoint, container: List[TimeRange]) -> List[bool]:
    return [check_timerange(member, tr) for tr in container]


def check_geoboxes(member: TrackPoint, container: List[GeoBox]) -> List[bool]:
    return [check_geobox(member, tr) for tr in container]


def check_geocircles(member: TrackPoint, container: List[GeoCircle]) -> List[bool]:
    return [check_geocircle(member, tr) for tr in container]


def edit_track(args: Namespace, track: RcTrack) -> Tuple[int, int]:
    """
    Iterate over the points in an RcTrack, and remove unwanted ones
    by subjecting them to a set of tests for exclusion based on time,
    presence inside a rectangular area, or distance from a location.

    The filter deletes from the end because this function will shorten
    the track by popping elements from the list of points. Once a point
    has survived filtering it is not referred to again and its index
    can change without ill effect.
    """

    if args.track_name is None:
        args.track_name = f"{track.name} (edit)"
    track.name = args.track_name

    before_len = len(track.points)
    for i in range(before_len - 1, -1, -1):
        if args.include_time_range:
            is_included_time = check_timeranges(track.points[i], args.include_time_range)
            if not any(is_included_time):
                track.points.pop(i)
                continue
        if args.exclude_time_range:
            is_excluded_time = check_timeranges(track.points[i], args.exclude_time_range)
            if any(is_excluded_time):
                track.points.pop(i)
                continue
        if args.include_geo:
            is_included_geo = check_geoboxes(track.points[i], args.include_geo)
            if not any(is_included_geo):
                track.points.pop(i)
                continue
        if args.exclude_geo:
            is_excluded_geo = check_geoboxes(track.points[i], args.exclude_geo)
            if any(is_excluded_geo):
                track.points.pop(i)
                continue
        if args.include_radius:
            is_included_radius = check_geocircles(track.points[i], args.include_radius)
            if not any(is_included_radius):
                track.points.pop(i)
                continue
        if args.exclude_radius:
            is_excluded_radius = check_geocircles(track.points[i], args.exclude_radius)
            if any(is_excluded_radius):
                track.points.pop(i)
                continue

    after_len = len(track.points)
    return (before_len, after_len)


def main() -> None:
    args = get_args()
    if args.long_help:
        long_help()

    if True:
        print("parsed args:")
        for x in dir(args):
            if x.startswith("_"):
                continue
            print(f"\t{x}: {getattr(args, x)}")
        print()

    # file deepcode ignore PT: Shut up snyk, this is a CLI utility intended to walk files...
    track = RcTrack()
    track.load_file(args.filename)
    l = edit_track(args, track)

    print(f"edit results: {l[0]} -> {l[1]} points")
    T_start = track.points[0].datetime.astimezone(localtz)
    T_end = track.points[-1].datetime.astimezone(localtz)
    duration = T_end - T_start
    print(f"track times: {T_start} -> {T_end}, duration={duration}")

    backup_file = f"{args.output}~"
    try:
        os.unlink(backup_file)
    except FileNotFoundError:
        pass
    try:
        os.link(args.output, backup_file)
    except FileNotFoundError:
        pass
    tfd, tfn = mkstemp(dir=os.path.dirname(args.filename))
    os.close(tfd)
    track.write_file(tfn)
    os.rename(tfn, args.output)


if __name__ == "__main__":
    main()
