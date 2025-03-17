#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# Author: Chris Kuethe <chris.kuethe@gmail.com> , https://github.com/ckuethe/radiacode-tools
# SPDX-License-Identifier: MIT

"""
Some stuff found to be useful in various scripts, and should thus be hoisted into a
utility library, rather than being imported from and between scripts.
"""

from datetime import datetime, timedelta
from re import match as re_match
from typing import Any, Dict, Tuple

from .rc_types import GeoBox, GeoCircle, GeoPoint, TimeRange
from .rc_utils import _BEGINNING_OF_TIME, _THE_END_OF_DAYS, UTC, localtz, parse_datetime

_LAT_MIN: float = -90
_LAT_MAX: float = 90
_LON_MIN: float = -180
_LON_MAX: float = 180
_DIST_MAX: float = 40030e3  # 3.1416 * 2 * 6371km
_SAMP_MAX: float = 2.0**32  # where are you getting 4.2 billion radiation measurement from?


def _rcsn(s: str) -> str:
    "helper to check the format of a radiacode serial number"
    if re_match(r"RC-\d{3}[G]?-\d{6}", s.strip()):
        return s
    raise ValueError("Incorrect serial number format")


def _isotime(s: str) -> datetime:
    """helper to enforce ISO8061 time string format

    MUST look like 'YYYY-mm-dd[T ]HH:MM:SSZ?'
    """
    s = s.strip()
    m = re_match(r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})Z?$", s)
    if m:
        return datetime(*[int(x, 10) for x in m.groups()], tzinfo=UTC if s.endswith("Z") else localtz)  # type: ignore
    else:
        raise ValueError("Invalid time format")


def _timerange(s: str = "~") -> TimeRange:
    """
    argparse helper to validate a timerange (a pair of datetimes)

    Either end can be unspecified, in which case it will be treated
    as the start or end of time (or at least the unix epoch).
    """
    w = s.split("~")
    if len(w) != 2:
        raise ValueError
    a = _BEGINNING_OF_TIME
    b = _THE_END_OF_DAYS
    if w[0]:
        a = _isotime(w[0]).replace(tzinfo=UTC if w[0].endswith("Z") else localtz)
    if w[1]:
        b = _isotime(w[1]).replace(tzinfo=UTC if w[1].endswith("Z") else localtz)
    return TimeRange(a, b)


def _geobox(s: str) -> GeoBox:
    """
    argparse helper to validate a box geometry specified by two diagonal corners

    geobox is specified by a string of the form lat1,lon1~lat2,lon2 where

        -90 <= lat <= 90
        -180 <= lon <= 180
    """
    points = s.split("~")
    p0 = [float(f) for f in points[0].split(",")]
    p1 = [float(f) for f in points[1].split(",")]

    if (
        True
        and 2 == len(points)
        and 2 == len(p0)
        and 2 == len(p1)
        and _LAT_MIN <= p0[0] <= _LAT_MAX
        and _LAT_MIN <= p1[0] <= _LAT_MAX
        and _LON_MIN <= p0[1] <= _LON_MAX
        and _LON_MIN <= p1[1] <= _LON_MAX
    ):
        return GeoBox(GeoPoint(*p0), GeoPoint(*p1))
    raise ValueError


def _geocircle(s: str) -> GeoCircle:
    """
    argparse helper to validate a geocircle; a radius around a point formatted
    as latitude,longitude,radius_m where

        -90 <= latitude <= 90 degrees
        -180 <= latitude <= 180 degrees
        0 < radius < 40030e3 meters
    """
    rv = [float(f) for f in s.split(",")]
    if (
        True
        and (3 == len(rv))
        and (_LON_MIN <= rv[0] <= _LON_MAX)
        and (_LAT_MIN <= rv[1] <= _LAT_MAX)
        and (0 < rv[2] <= _DIST_MAX)
    ):
        return GeoCircle(GeoPoint(rv[0], rv[1]), rv[2])
    raise ValueError


def _duration_range(s: str = "~") -> Tuple[int, int]:
    """
    Argparse helpter to validate some time ranges, returning a pair of floating point seconds

    Examples
    00:00:00~23:19:00
    12:34:56~
    ~12:34:56
    """
    w = s.split("~")
    if 2 != len(w):
        raise ValueError
    a = 0.0
    b = _SAMP_MAX
    if w[0]:
        t = [_non_negative_int(x) for x in w[0].split(":")]
        if 3 != len(t):
            raise ValueError
        a = timedelta(hours=t[0], minutes=t[1], seconds=t[2]).total_seconds()
    if w[1]:
        t = [_non_negative_int(x) for x in w[1].split(":")]
        if 3 != len(t):
            raise ValueError
        b = timedelta(hours=t[0], minutes=t[1], seconds=t[2]).total_seconds()
    return int(a), int(b)


def _samp_range(s: str = "~") -> Tuple[int, int]:
    "Check that a string of the form 'start~end' can be converted into two non-negative integers"
    w = s.split("~")
    if 2 != len(w):
        raise ValueError
    a = 0
    b = int(_SAMP_MAX)
    if w[0]:
        a = _non_negative_int(w[0])
    if w[1]:
        b = _non_negative_int(w[1])

    return a, b


def _non_negative_int(s: str) -> int:
    "check that a string can be converted into a non-negative base-10 integer"
    fv = float(s)
    iv = int(fv)
    if fv - iv:  # check that fractional part is 0
        raise ValueError()
    if iv < 0:
        raise ValueError()
    return iv


def _positive_int(s: str) -> int:
    "check that a string can be converted into a positive base-10 integer"
    rv = _non_negative_int(s)
    if rv <= 0:
        raise ValueError()
    return int(rv)


def _positive_float(s: str) -> float:
    "check that a string can be converted into a positive float"
    rv = float(s)
    if rv > 0:
        return rv
    raise ValueError()


def _geometry(s: str) -> Tuple[int, int]:
    "check a geometry string of 'WxH' where W and H are positive integers"
    n = s.strip().split("x")
    if len(n) != 2:
        raise ValueError()
    return _positive_int(n[0]), _positive_int(n[1])


def _gpsd(s) -> Dict[str, Any] | None:
    m = re_match(r"^gpsd://(?P<host>[a-zA-Z0-9_.-]+)(:(?P<port>\d+))?(?P<device>/.+)?", s)
    if m:
        return m.groupdict()
    else:
        return None
