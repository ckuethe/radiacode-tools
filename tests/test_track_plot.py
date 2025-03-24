#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

from os.path import dirname
from os.path import join as pathjoin
from unittest.mock import patch

import pytest

testdir = pathjoin(dirname(__file__), "data")
testfile = pathjoin(testdir, "walk.rctrk")

from radiacode_tools.rc_files import RcTrack
from track_plot import (
    downsample_trackpoints,
    get_args,
    map_ctr,
    mean,
    osm_zoom,
    tracklist_range_probe,
)


def test_argparse_no_args():
    with patch("sys.argv", [__file__]):
        with pytest.raises(SystemExit):
            get_args()


def test_argparse_default():
    with patch("sys.argv", [__file__, testfile]):
        a = get_args()
        assert a.input_file == testfile


def test_map_ctr():
    bbx = {"latitude": (0, 1), "longitude": (0, 1)}
    rv = map_ctr(bbx)
    assert rv == {"lat": 0.5, "lon": 0.5}


def test_mean():
    l = range(11)
    m = mean(l)
    assert 5 == m


def test_mean_empty():
    with pytest.raises(ZeroDivisionError):
        mean([])


def test_mean_bogus():
    with pytest.raises(TypeError):
        mean("string")


def test_funcs():
    tk = RcTrack(testfile)
    tr = tracklist_range_probe(tk.points)

    # did range_probe measure the track length properly?
    assert tr["len"] == len(tk.points)

    # downsampling by 1 should be a no-op
    points = downsample_trackpoints(tk.points, 1)
    assert len(points) == len(tk.points)

    downsampling = 4
    points = downsample_trackpoints(tk.points, downsampling)
    assert pytest.approx(len(points), abs=downsampling) == len(tk.points) // downsampling


def test_osm_zoom():
    tests = [
        ({"latitude": (-90, 90.0), "longitude": (-180, 180)}, 2),  # Whole planet
        ({"latitude": (24.4, 49.0), "longitude": (-125.3, -66.87)}, 4),  # CONUS
        ({"latitude": (37.888440, 36.469434), "longitude": (-115.299663, -117.095783)}, 9),  # Spooky stuff
        ({"latitude": (33.681186, 33.673443), "longitude": (-106.480745, -106.470778)}, 15),  # Trinity
    ]

    for t in tests:
        assert t[1] == osm_zoom(t[0])
