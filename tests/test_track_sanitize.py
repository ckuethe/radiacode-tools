#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import unittest
from os.path import dirname
from os.path import join as pathjoin
from unittest.mock import patch

testdir = pathjoin(dirname(__file__), "data")
testfile = pathjoin(testdir, "walk.rctrk")

from radiacode_tools.rc_files import RcTrack
from track_sanitize import RangeFinder, get_args, sanitize


class TestTrackSanitize(unittest.TestCase):
    def test_argparse_no_args(self):
        with patch("sys.argv", [__file__]):
            with self.assertRaises(SystemExit):
                get_args()

    def test_default_sanitize(self):
        with patch("sys.argv", [__file__, testfile]):
            a = get_args()
            self.assertEqual(testfile, a.files[0])

        track = RcTrack(a.files[0])

        sanitize(a, track)

        rf_lon = RangeFinder()
        rf_lat = RangeFinder()
        rf_time = RangeFinder()
        rf_lon.add([x.longitude for x in track.points])
        rf_lat.add([x.latitude for x in track.points])
        rf_time.add([x.datetime for x in track.points])

        # Check that metadata was scrubbed
        self.assertEqual(track.comment, a.comment)
        self.assertEqual(track.serialnumber, a.serial_number)
        self.assertEqual(track.name[: len(a.prefix)], a.prefix)
        self.assertEqual(len(track.name), len(a.prefix) + 32)

        # check that rebase occurred successfully
        self.assertEqual(rf_lon.min_val, a.base_longitude)
        self.assertEqual(rf_lat.min_val, a.base_latitude)
        self.assertEqual(rf_time.min_val, a.start_time)

    def test_limited_sanitize(self):
        with patch("sys.argv", [__file__, "-CNS", testfile]):
            a = get_args()
            self.assertEqual(testfile, a.files[0])

        track = RcTrack(a.files[0])
        orig_comment = track.comment
        orig_serial = track.serialnumber
        orig_name = track.name

        sanitize(a, track)

        # it has been established that sanitize can scrub everything correctly,
        # now test that some metadata is preserved if so desired
        self.assertEqual(track.comment, orig_comment)
        self.assertEqual(track.serialnumber, orig_serial)
        self.assertEqual(track.name, orig_name)
