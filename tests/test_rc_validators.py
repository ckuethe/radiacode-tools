#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import unittest

from radiacode_tools import rc_validators
from radiacode_tools.rc_types import GeoCircle, GeoPoint
from radiacode_tools.rc_utils import _BEGINNING_OF_TIME, _BEGINNING_OF_TIME_STR


class TestRcValidators(unittest.TestCase):
    def test_positive_float(self):
        v = 1.0
        self.assertEqual(v, rc_validators._positive_float(str(v)))
        self.assertEqual(v, rc_validators._positive_float(int(v)))
        self.assertEqual(v, rc_validators._positive_float(v))
        with self.assertRaises(ValueError):
            _ = rc_validators._positive_float("0.0")
        with self.assertRaises(ValueError):
            _ = rc_validators._positive_float("-1.0")
        with self.assertRaises(ValueError):
            _ = rc_validators._positive_float("string")

    def test_non_negattve_int(self):
        v = 0
        self.assertEqual(v, rc_validators._non_negative_int(str(v)))
        self.assertEqual(v, rc_validators._non_negative_int(f"0{v}"))  # leading zeros are ok
        self.assertEqual(v, rc_validators._non_negative_int(float(v)))
        self.assertEqual(v, rc_validators._non_negative_int(v))
        with self.assertRaises(ValueError):
            _ = rc_validators._non_negative_int("1.1")
        with self.assertRaises(ValueError):
            _ = rc_validators._non_negative_int("-1")
        with self.assertRaises(ValueError):
            _ = rc_validators._non_negative_int("string")

    def test_positive_int(self):
        v = 10
        self.assertEqual(v, rc_validators._positive_int(str(v)))
        self.assertEqual(v, rc_validators._positive_int(f"0{v}"))  # leading zeros are ok
        self.assertEqual(v, rc_validators._positive_int(float(v)))
        self.assertEqual(v, rc_validators._positive_int(v))
        with self.assertRaises(ValueError):
            _ = rc_validators._positive_int("0")
        with self.assertRaises(ValueError):
            _ = rc_validators._positive_int("1.1")
        with self.assertRaises(ValueError):
            _ = rc_validators._positive_int("-1")
        with self.assertRaises(ValueError):
            _ = rc_validators._positive_int("string")

    def test_rcsn(self):
        g = "RC-103G-314159"
        s = g.replace("G", "")
        x = g.replace("G", "X")
        gl = g.lower()
        sl = s.lower()
        xl = x.lower()

        self.assertEqual(g, rc_validators._rcsn(g))
        self.assertEqual(s, rc_validators._rcsn(s))
        with self.assertRaises(ValueError):
            _ = rc_validators._rcsn(x)

        with self.assertRaises(ValueError):
            _ = rc_validators._rcsn(gl)

        with self.assertRaises(ValueError):
            _ = rc_validators._rcsn(sl)

        with self.assertRaises(ValueError):
            _ = rc_validators._rcsn(xl)

    def test_isotime(self):
        eqval = _BEGINNING_OF_TIME
        self.assertEqual(eqval, rc_validators._isotime(_BEGINNING_OF_TIME_STR))
        self.assertEqual(eqval, rc_validators._isotime(_BEGINNING_OF_TIME_STR.replace(" ", "T")))
        with self.assertRaises(ValueError):
            _ = rc_validators._isotime("not a real timestamp")

    def test_geometry(self):
        self.assertEqual((640, 480), rc_validators._geometry("640x480"))
        with self.assertRaises(ValueError):
            _ = rc_validators._geometry("0x0")
        with self.assertRaises(ValueError):
            _ = rc_validators._geometry("1x2x3")

    def test_geocircle(self):
        gc = rc_validators._geocircle("1,2,3")
        self.assertEqual(GeoCircle(point=GeoPoint(latitude=1, longitude=2), radius=3), gc)
        with self.assertRaises(ValueError):
            _ = rc_validators._geocircle("0,0,0")  # invalid radius
        with self.assertRaises(ValueError):
            _ = rc_validators._geocircle("-360,0,0")  # invalid latitude
        with self.assertRaises(ValueError):
            _ = rc_validators._geocircle("0,-360,0")  # invalid longitude
        with self.assertRaises(ValueError):
            _ = rc_validators._geocircle("1,1")  # missing radius
        with self.assertRaises(ValueError):
            _ = rc_validators._geocircle("1,1,1,1")  # extra args

    def test_geobox(self):
        gb = rc_validators._geobox("-1,-2~3,4")
        self.assertEqual(gb.p2.latitude, 3)
        with self.assertRaises(ValueError):
            _ = rc_validators._geobox("")  # invalid empty string
        with self.assertRaises(ValueError):
            _ = rc_validators._geobox("~")  # no points
        with self.assertRaises(ValueError):
            _ = rc_validators._geobox("~1,1")  # missing start
        with self.assertRaises(ValueError):
            _ = rc_validators._geobox("1,1~1")  # missing end
        with self.assertRaises(ValueError):
            _ = rc_validators._geobox("1,1~")  # missing end
        with self.assertRaises(ValueError):
            _ = rc_validators._geobox("0,0~1,1~2,2")  # extra point

    def test_samp_range(self):
        s0 = rc_validators._samp_range()
        self.assertEqual((0, rc_validators._SAMP_MAX), s0)
        s1 = rc_validators._samp_range("0~")
        self.assertEqual((0, rc_validators._SAMP_MAX), s1)
        s2 = rc_validators._samp_range("10~20")
        self.assertEqual((10, 20), s2)
        s3 = rc_validators._samp_range("~42")
        self.assertEqual((0, 42), s3)
        with self.assertRaises(ValueError):
            _ = rc_validators._samp_range("")
        with self.assertRaises(ValueError):
            _ = rc_validators._samp_range("1~2~3")
        with self.assertRaises(ValueError):
            _ = rc_validators._samp_range("-1~2")

    def test_time_range(self):
        rv = rc_validators._timerange()
        self.assertEqual((rc_validators._BEGINNING_OF_TIME, rc_validators._THE_END_OF_DAYS), rv)

        with self.assertRaises(ValueError):
            rc_validators._timerange("1~2~4")
        with self.assertRaises(ValueError):
            rc_validators._timerange("x~")
        with self.assertRaises(ValueError):
            rc_validators._timerange("~x")

    def test_duration_range(self):
        rv = rc_validators._duration_range()
        self.assertEqual((0, rc_validators._SAMP_MAX), rv)
        rv = rc_validators._duration_range("1:2:4~2:01:10")
        self.assertEqual((4 + 2 * 60 + 1 * 60 * 60, 10 + 1 * 60 + 2 * 60 * 60), rv)
        with self.assertRaises(ValueError):
            rc_validators._duration_range("1:00~23:19")
        with self.assertRaises(ValueError):
            rc_validators._duration_range("1~2~4")
        with self.assertRaises(ValueError):
            rc_validators._duration_range("-1~")
        with self.assertRaises(ValueError):
            rc_validators._duration_range("~10000000000")

    def test_gpsd(self):
        g = rc_validators._gpsd("")
        self.assertIsNone(g)
        g = rc_validators._gpsd("nope")
        self.assertIsNone(g)
        g = rc_validators._gpsd("gpsd://127.0.0.1:12345/dev/fakegps")
        self.assertEqual(g, {"host": "127.0.0.1", "port": "12345", "device": "/dev/fakegps"})
        g = rc_validators._gpsd("gpsd://127.0.0.1/")
        self.assertEqual(g, {"host": "127.0.0.1", "port": None, "device": None})
        g = rc_validators._gpsd("gpsd://127.0.0.1/dev/fakegps")
        self.assertEqual(g, {"host": "127.0.0.1", "port": None, "device": "/dev/fakegps"})
        g = rc_validators._gpsd("gpsd://127.0.0.1:12345")
        self.assertEqual(g, {"host": "127.0.0.1", "port": "12345", "device": None})
