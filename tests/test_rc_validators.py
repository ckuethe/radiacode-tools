#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import pytest

from radiacode_tools import rc_validators
from radiacode_tools.rc_types import GeoCircle, GeoPoint, TimeRange
from radiacode_tools.rc_utils import _BEGINNING_OF_TIME, _BEGINNING_OF_TIME_STR


def test_positive_float():
    v = 1.0
    assert v == rc_validators._positive_float(str(v))
    assert v == rc_validators._positive_float(int(v))
    assert v == rc_validators._positive_float(v)
    with pytest.raises(ValueError):
        _ = rc_validators._positive_float("0.0")
    with pytest.raises(ValueError):
        _ = rc_validators._positive_float("-1.0")
    with pytest.raises(ValueError):
        _ = rc_validators._positive_float("string")


def test_non_negattve_int():
    v = 0
    assert v == rc_validators._non_negative_int(str(v))
    assert v == rc_validators._non_negative_int(f"0{v}")  # leading zeros are ok
    assert v == rc_validators._non_negative_int(float(v))
    assert v == rc_validators._non_negative_int(v)
    with pytest.raises(ValueError):
        _ = rc_validators._non_negative_int("1.1")
    with pytest.raises(ValueError):
        _ = rc_validators._non_negative_int("-1")
    with pytest.raises(ValueError):
        _ = rc_validators._non_negative_int("string")


def test_positive_int():
    v = 10
    assert v == rc_validators._positive_int(str(v))
    assert v == rc_validators._positive_int(f"0{v}")  # leading zeros are ok
    assert v == rc_validators._positive_int(float(v))
    assert v == rc_validators._positive_int(v)
    with pytest.raises(ValueError):
        _ = rc_validators._positive_int("0")
    with pytest.raises(ValueError):
        _ = rc_validators._positive_int("1.1")
    with pytest.raises(ValueError):
        _ = rc_validators._positive_int("-1")
    with pytest.raises(ValueError):
        _ = rc_validators._positive_int("string")


def test_rcsn():
    g = "RC-103G-314159"
    s = g.replace("G", "")
    x = g.replace("G", "X")
    gl = g.lower()
    sl = s.lower()
    xl = x.lower()

    assert g == rc_validators._rcsn(g)
    assert s == rc_validators._rcsn(s)
    with pytest.raises(ValueError):
        _ = rc_validators._rcsn(x)

    with pytest.raises(ValueError):
        _ = rc_validators._rcsn(gl)

    with pytest.raises(ValueError):
        _ = rc_validators._rcsn(sl)

    with pytest.raises(ValueError):
        _ = rc_validators._rcsn(xl)


def test_isotime():
    eqval = _BEGINNING_OF_TIME
    assert eqval == rc_validators._isotime(_BEGINNING_OF_TIME_STR)
    assert eqval == rc_validators._isotime(_BEGINNING_OF_TIME_STR.replace(" ", "T"))
    with pytest.raises(ValueError):
        _ = rc_validators._isotime("not a real timestamp")


def test_geometry():
    assert rc_validators._geometry("640x480") == (640, 480)
    with pytest.raises(ValueError):
        _ = rc_validators._geometry("0x0")
    with pytest.raises(ValueError):
        _ = rc_validators._geometry("1x2x3")


def test_geocircle():
    gc = rc_validators._geocircle("1,2,3")
    assert GeoCircle(point=GeoPoint(latitude=1, longitude=2), radius=3) == gc
    gc = rc_validators._geocircle("33.95,-118.41,3")
    assert GeoCircle(point=GeoPoint(latitude=33.95, longitude=-118.41), radius=3) == gc
    with pytest.raises(ValueError):
        _ = rc_validators._geocircle("0,0,0")  # invalid radius
    with pytest.raises(ValueError):
        _ = rc_validators._geocircle("-360,0,0")  # invalid latitude
    with pytest.raises(ValueError):
        _ = rc_validators._geocircle("0,-360,0")  # invalid longitude
    with pytest.raises(ValueError):
        _ = rc_validators._geocircle("1,1")  # missing radius
    with pytest.raises(ValueError):
        _ = rc_validators._geocircle("1,1,1,1")  # extra args


def test_geobox():
    gb = rc_validators._geobox("-1,-2~3,4")
    assert gb.p2.latitude == 3
    with pytest.raises(ValueError):
        _ = rc_validators._geobox("")  # invalid empty string
    with pytest.raises(ValueError):
        _ = rc_validators._geobox("~")  # no points
    with pytest.raises(ValueError):
        _ = rc_validators._geobox("~1,1")  # missing start
    with pytest.raises(ValueError):
        _ = rc_validators._geobox("1,1~1")  # missing end
    with pytest.raises(ValueError):
        _ = rc_validators._geobox("1,1~")  # missing end
    with pytest.raises(ValueError):
        _ = rc_validators._geobox("0,0~1,1~2,2")  # extra point


def test_samp_range():
    s0 = rc_validators._samp_range()
    assert (0, rc_validators._SAMP_MAX) == s0
    s1 = rc_validators._samp_range("0~")
    assert (0, rc_validators._SAMP_MAX) == s1
    s2 = rc_validators._samp_range("10~20")
    assert (10, 20) == s2
    s3 = rc_validators._samp_range("~42")
    assert (0, 42) == s3
    with pytest.raises(ValueError):
        _ = rc_validators._samp_range("")
    with pytest.raises(ValueError):
        _ = rc_validators._samp_range("1~2~3")
    with pytest.raises(ValueError):
        _ = rc_validators._samp_range("-1~2")


def test_time_range():
    rv = rc_validators._timerange()
    assert TimeRange(dt_start=rc_validators._BEGINNING_OF_TIME, dt_end=rc_validators._THE_END_OF_DAYS) == rv

    with pytest.raises(ValueError):
        rc_validators._timerange("1~2~4")
    with pytest.raises(ValueError):
        rc_validators._timerange("x~")
    with pytest.raises(ValueError):
        rc_validators._timerange("~x")


def test_duration_range():
    rv = rc_validators._duration_range()
    assert (0, rc_validators._SAMP_MAX) == rv
    rv = rc_validators._duration_range("1:2:4~2:01:10")
    assert (4 + 2 * 60 + 1 * 60 * 60, 10 + 1 * 60 + 2 * 60 * 60) == rv
    with pytest.raises(ValueError):
        rc_validators._duration_range("1:00~23:19")
    with pytest.raises(ValueError):
        rc_validators._duration_range("1~2~4")
    with pytest.raises(ValueError):
        rc_validators._duration_range("-1~")
    with pytest.raises(ValueError):
        rc_validators._duration_range("~10000000000")


def test_gpsd():
    g = rc_validators._gpsd("")
    assert g is None
    g = rc_validators._gpsd("nope")
    assert g is None
    g = rc_validators._gpsd("gpsd://127.0.0.1:12345/dev/fakegps")
    assert g == {"host": "127.0.0.1", "port": "12345", "device": "/dev/fakegps"}
    g = rc_validators._gpsd("gpsd://127.0.0.1/")
    assert g == {"host": "127.0.0.1", "port": None, "device": None}
    g = rc_validators._gpsd("gpsd://127.0.0.1/dev/fakegps")
    assert g == {"host": "127.0.0.1", "port": None, "device": "/dev/fakegps"}
    g = rc_validators._gpsd("gpsd://127.0.0.1:12345")
    assert g == {"host": "127.0.0.1", "port": "12345", "device": None}
