#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import datetime
from os.path import dirname
from os.path import join as pathjoin

import pytest

testdir = pathjoin(dirname(__file__), "data")
testfile = pathjoin(testdir, "walk.rctrk")

from radiacode_tools.rc_files import RcTrack
from radiacode_tools.rc_utils import UTC
from track_sanitize import RangeFinder, get_args, main, sanitize


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


def test_main(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, "-o", testfile])
    assert main() is None


def test_limited_sanitize(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, "-PTCNS", testfile])
    a = get_args()
    assert testfile == a.files[0]

    track = RcTrack(a.files[0])
    orig_comment = track.comment
    orig_serial = track.serialnumber
    orig_name = track.name
    orig_ends = (track.points[0], track.points[-1])

    sanitize(a, track)

    # it has been established that sanitize can scrub everything correctly,
    # now test that some metadata is preserved if so desired
    assert track.comment == orig_comment
    assert track.serialnumber == orig_serial
    assert track.name == orig_name
    assert (track.points[0], track.points[-1]) == orig_ends


def test_reverse_sanitize(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, "-PTR", testfile])
    a = get_args()
    assert testfile == a.files[0]

    # Test track starts at 2025-01-01T00:00:00Z, latitude/longitude = (0,0)
    # Test moves 1 degree North and East per minute
    # Test ends at  2025-01-01T00:09:00Z, latitude/longitude = (9,9)
    locations_source = []
    times_source = []

    track = RcTrack()
    for i in range(10):
        dt = datetime.datetime(2025, 1, 1, 0, i, 0, tzinfo=UTC)
        track.add_point(
            dt=dt,
            latitude=i,
            longitude=i,
            accuracy=1,
            dose_rate=1,
            count_rate=1,
        )
        locations_source.append((i, i))
        times_source.append(dt)

    # extract times and locations from the RcTrack object
    locations_track_orig = [(p.latitude, p.longitude) for p in track.points]
    times_track_orig = [p.datetime for p in track.points]

    # Verify that our position and time recorded in the track is as expected
    assert locations_track_orig == locations_source
    assert times_track_orig == times_source

    # do the sanitize operation, which may call reverse_route()
    sanitize(a, track)

    # extract times and locations from the RcTrack object
    times_track_edited = [p.datetime for p in track.points]
    locations_track_edited = [(p.latitude, p.longitude) for p in track.points]

    # Verify that our position and time recorded in the track have been edited correctly
    assert times_track_edited == times_source
    assert locations_track_edited == locations_source[::-1]
