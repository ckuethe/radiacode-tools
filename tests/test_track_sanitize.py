#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

from os.path import dirname
from os.path import join as pathjoin

import pytest

testdir = pathjoin(dirname(__file__), "data")
testfile = pathjoin(testdir, "walk.rctrk")

from radiacode_tools.rc_files import RcTrack
from track_sanitize import RangeFinder, get_args, sanitize


def test_argparse_no_args(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__])
    with pytest.raises(SystemExit):
        get_args()


def test_default_sanitize(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, testfile])
    a = get_args()
    assert testfile == a.files[0]

    track = RcTrack(a.files[0])

    sanitize(a, track)

    rf_lon = RangeFinder()
    rf_lat = RangeFinder()
    rf_time = RangeFinder()
    rf_lon.add([x.longitude for x in track.points])
    rf_lat.add([x.latitude for x in track.points])
    rf_time.add([x.datetime for x in track.points])

    # Check that metadata was scrubbed
    assert track.comment == a.comment
    assert track.serialnumber == a.serial_number
    assert track.name[: len(a.prefix)] == a.prefix
    assert len(track.name) == len(a.prefix) + 32

    # check that rebase occurred successfully
    assert rf_lon.min_val == a.base_longitude
    assert rf_lat.min_val == a.base_latitude
    assert rf_time.min_val == a.start_time


def test_limited_sanitize(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, "-CNS", testfile])
    a = get_args()
    assert testfile == a.files[0]

    track = RcTrack(a.files[0])
    orig_comment = track.comment
    orig_serial = track.serialnumber
    orig_name = track.name

    sanitize(a, track)

    # it has been established that sanitize can scrub everything correctly,
    # now test that some metadata is preserved if so desired
    assert track.comment == orig_comment
    assert track.serialnumber == orig_serial
    assert track.name == orig_name
