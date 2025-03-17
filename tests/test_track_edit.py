#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import unittest
from datetime import datetime
from os.path import dirname
from os.path import join as pathjoin
from unittest.mock import patch

testdir = pathjoin(dirname(__file__), "data")
testfile = pathjoin(testdir, "walk.rctrk")

from radiacode_tools.rc_files import RcTrack
from radiacode_tools.rc_types import GeoBox, GeoCircle, GeoPoint, TimeRange, TrackPoint
from track_edit import (
    check_geoboxes,
    check_geocircles,
    check_timeranges,
    earthdistance,
    edit_track,
    get_args,
)


class TestTrackEdit(unittest.TestCase):
    def test_argparse_no_args(self):
        with patch("sys.argv", [__file__]):
            with self.assertRaises(SystemExit):
                get_args()

    def test_argparse_filename(self):
        with patch("sys.argv", [__file__, testfile]):
            a = get_args()
            self.assertEqual(testfile, a.filename)

    def test_earthdistance1(self):
        # haversine assumes spherical earth. The circumference of the earth is about
        # 40075km around the equator, and 40007km through the poles. Let's average those
        # and take half that distance to estimate the distance between antipodes to be
        # about 20020km
        d_a = 20020
        tol = 10  # good enough for this approximation
        d_e = earthdistance(0, 0, 0, 180) / 1000
        d_p = earthdistance(-90, 0, 90, 0) / 1000
        self.assertEqual(d_e, d_p)  # this should be true assuming a spherical earth
        self.assertAlmostEqual(d_a, d_e, delta=tol)

    def test_earthdistance2(self):
        JFK = (40.7033448, -73.8919609)
        LAX = (33.9655136, -118.4181808)
        LHR = (51.4700628, -0.4559553)
        NRT = (35.7734217, 140.3875152)
        SFO = (37.6294499, -122.3582975)
        SYD = (-33.8766012, 151.1437224)
        tol = 10
        d_jfk_lon = earthdistance(*JFK, *LHR) / 1000
        d_lax_nrt = earthdistance(*LAX, *NRT) / 1000
        d_sfo_syd = earthdistance(*SFO, *SYD) / 1000
        # Distances computed using the calculator at https://www.nhc.noaa.gov/gccalc.shtml
        self.assertAlmostEqual(d_jfk_lon, 5539, delta=tol)
        self.assertAlmostEqual(d_lax_nrt, 8745, delta=tol)
        self.assertAlmostEqual(d_sfo_syd, 11942, delta=tol)

    def test_geoboxes(self):
        tp_in = TrackPoint(latitude=1, longitude=1)
        tp_out = TrackPoint(latitude=20, longitude=20)
        containers = [
            GeoBox(p1=GeoPoint(0, 0), p2=GeoPoint(2, 2)),
            GeoBox(p1=GeoPoint(4, 4), p2=GeoPoint(2, 2)),
        ]
        self.assertTrue(any(check_geoboxes(tp_in, containers)))
        self.assertFalse(any(check_geoboxes(tp_out, containers)))
        with self.assertRaises(ValueError):
            check_geoboxes(tp_in, containers[0])

    def test_geocircles(self):
        tp_in = TrackPoint(latitude=0.00001, longitude=0.0001)
        tp_out = TrackPoint(latitude=20, longitude=20)
        containers = [
            GeoCircle(GeoPoint(0, 0), 10000),
            GeoCircle(GeoPoint(1, 1), 10000),
        ]
        self.assertTrue(any(check_geocircles(tp_in, containers)))
        self.assertFalse(any(check_geocircles(tp_out, containers)))
        with self.assertRaises(ValueError):
            check_geocircles(tp_in, containers[0])

    def test_timeranges(self):
        tp_in = TrackPoint(latitude=0, longitude=0, datetime=datetime(2000, 2, 1, 0, 0, 0))
        tp_out = TrackPoint(latitude=0, longitude=0, datetime=datetime(2000, 3, 15, 0, 0, 0))
        containers = [
            TimeRange(t_start=datetime(2000, 1, 1, 0, 0, 0), t_end=datetime(2000, 2, 1, 0, 0, 0)),
            TimeRange(t_start=datetime(2000, 2, 1, 0, 0, 0), t_end=datetime(2000, 3, 1, 0, 0, 0)),
        ]
        self.assertTrue(any(check_timeranges(tp_in, containers)))
        self.assertFalse(any(check_timeranges(tp_out, containers)))
        with self.assertRaises(ValueError):
            check_timeranges(tp_in, containers[0])

    def test_edit_track_noop(self):
        with patch("sys.argv", [__file__, testfile]):
            args = get_args()
            track = RcTrack(args.filename)
            a, b = edit_track(args, track)
            self.assertEqual(a, b)
            self.assertGreater(b, 0)

    def test_edit_track_exclude_timerange_all(self):
        with patch("sys.argv", [__file__, "-n", "exclude_timerange_test", "-T", "~", testfile]):
            args = get_args()
            track = RcTrack(args.filename)
            a, b = edit_track(args, track)
            self.assertEqual(0, b)

    def test_edit_track_exclude_timerange_none(self):
        with patch("sys.argv", [__file__, "-n", "exclude_timerange_test", "-T", "~2000-01-01T00:00:00Z", testfile]):
            args = get_args()
            track = RcTrack(args.filename)
            a, b = edit_track(args, track)
            self.assertEqual(a, b)

    def test_edit_track_include_timerange_all(self):
        with patch("sys.argv", [__file__, "-n", "include_timerange_test", "-t", "~", testfile]):
            args = get_args()
            track = RcTrack(args.filename)
            a, b = edit_track(args, track)
            self.assertEqual(a, b)

    def test_edit_track_include_timerange_none(self):
        with patch("sys.argv", [__file__, "-n", "include_timerange_test", "-t", "~2000-01-01T00:00:00Z", testfile]):
            args = get_args()
            track = RcTrack(args.filename)
            a, b = edit_track(args, track)
            self.assertEqual(0, b)

    def test_edit_track_include_geocircle_all(self):
        with patch("sys.argv", [__file__, "-n", "include_geocircle_test", "-r", "0,0,1000", testfile]):
            args = get_args()
            track = RcTrack(args.filename)
            a, b = edit_track(args, track)
            self.assertEqual(a, b)

    def test_edit_track_include_geocircle_none(self):
        with patch("sys.argv", [__file__, "-n", "include_geocircle_test", "-r", "1,1,1000", testfile]):
            args = get_args()
            track = RcTrack(args.filename)
            a, b = edit_track(args, track)
            self.assertEqual(0, b)

    def test_edit_track_exclude_geocircle_all(self):
        with patch("sys.argv", [__file__, "-n", "exclude_geocircle_test", "-R", "0,0,1000", testfile]):
            args = get_args()
            track = RcTrack(args.filename)
            a, b = edit_track(args, track)
            self.assertEqual(0, b)

    def test_edit_track_exclude_geocircle_none(self):
        with patch("sys.argv", [__file__, "-n", "exclude_geocircle_test", "-R", "1,1,1000", testfile]):
            args = get_args()
            track = RcTrack(args.filename)
            a, b = edit_track(args, track)
            self.assertEqual(a, b)

    def test_edit_track_include_geobox_all(self):
        with patch("sys.argv", [__file__, "-n", "include_geobox_test", "-g", "0,0~1,1", testfile]):
            args = get_args()
            track = RcTrack(args.filename)
            a, b = edit_track(args, track)
            self.assertEqual(a, b)

    def test_edit_track_include_geobox_none(self):
        with patch("sys.argv", [__file__, "-n", "include_geobox_test", "-g", "1,1~2,2", testfile]):
            args = get_args()
            track = RcTrack(args.filename)
            a, b = edit_track(args, track)
            self.assertEqual(0, b)

    def test_edit_track_exclude_geobox_all(self):
        with patch("sys.argv", [__file__, "-n", "exclude_geobox_test", "-G", "0,0~1,1", testfile]):
            args = get_args()
            track = RcTrack(args.filename)
            a, b = edit_track(args, track)
            self.assertEqual(0, b)

    def test_edit_track_exclude_geobox_none(self):
        with patch("sys.argv", [__file__, "-n", "exclude_geobox_test", "-G", "1,1~2,2", testfile]):
            args = get_args()
            track = RcTrack(args.filename)
            a, b = edit_track(args, track)
            self.assertEqual(a, b)
