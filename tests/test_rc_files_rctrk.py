#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

from datetime import datetime
from io import StringIO
from os.path import dirname
from os.path import join as pathjoin

import pytest

from radiacode_tools.rc_files import _RCTRK_DEFAULT_NO_SERIAL_NUMBER, RcTrack
from radiacode_tools.rc_types import RcJSONEncoder
from radiacode_tools.rc_utils import _BEGINNING_OF_TIME, _BEGINNING_OF_TIME_STR, UTC

testdir = pathjoin(dirname(__file__), "data")


def test_rctrk(monkeypatch):
    tk = RcTrack()
    tk.add_point(dt=_BEGINNING_OF_TIME, latitude=0.0, longitude=0.0, accuracy=1.0, dose_rate=1.0, count_rate=1.0)
    assert str(tk)

    mock_ofd = StringIO()
    monkeypatch.setattr("builtins.open", lambda _filename, _mode: mock_ofd)
    monkeypatch.setattr(mock_ofd, "close", lambda: True)
    tk.write_file("/dev/stdout")

    # check that output looks vaguely reasonable
    generated_track = mock_ofd.getvalue().splitlines()
    assert len(generated_track) == 3, "two header lines and one data point"
    assert len(generated_track[-1].split("\t")) == 8, "there are 8 tab-delimited fields"


def test_rctrk_dict_jsonify():
    tk1 = RcTrack(pathjoin(testdir, "walk.rctrk"))
    jt = RcJSONEncoder().encode(tk1)
    assert jt


def test_rctrk_dict_roundtrip():
    tk1 = RcTrack(pathjoin(testdir, "walk.rctrk"))
    tk2 = RcTrack()

    tk2.from_dict(tk1.as_dict())
    assert len(tk1.points) == len(tk2.points)
    assert tk1.points[0].dt == tk2.points[0].dt


def test_rctrk_file_roundtrip(monkeypatch):
    tk1 = RcTrack(pathjoin(testdir, "walk.rctrk"))

    mock_ofd = StringIO()
    monkeypatch.setattr("builtins.open", lambda _filename, _mode: mock_ofd)
    monkeypatch.setattr(mock_ofd, "close", lambda: True)
    tk1.write_file("/dev/stdout")
    generated_track = mock_ofd.getvalue()

    mock_ifd = StringIO(generated_track)
    monkeypatch.setattr("builtins.open", lambda _filename, _mode: mock_ifd)
    monkeypatch.setattr(mock_ifd, "close", lambda: True)
    tk2 = RcTrack()
    tk2.load_file("/dev/stdin")
    assert len(tk1.points) == len(tk2.points)


def test_rctrk_bogus():
    tk = RcTrack()
    with pytest.raises(ValueError):
        tk.from_dict(dict())

    with pytest.raises(ValueError, match="missing header"):
        tk = RcTrack(__file__)  # of course this script isn't a valid track


def test_rctrk_null(monkeypatch):
    tk = RcTrack()
    assert tk.timestamp >= _BEGINNING_OF_TIME

    mock_ofd = StringIO()
    monkeypatch.setattr("builtins.open", lambda _filename, _mode: mock_ofd)
    monkeypatch.setattr(mock_ofd, "close", lambda: True)

    assert not tk.name  # Track name was unset
    tk.write_file("/dev/stdout")
    assert tk.name.startswith("Track")  # A default track name was generated when the track was written

    # check that output looks vaguely reasonable
    generated_track = mock_ofd.getvalue().splitlines()
    fields = generated_track[0].split("\t")
    assert fields[0].startswith("Track:")
    assert fields[0].endswith(tk.name)
    assert fields[1] == _RCTRK_DEFAULT_NO_SERIAL_NUMBER
    assert not fields[2]  # No comment
    assert fields[3] == "EC"

    assert len(generated_track[-1].split("\t")) == 8, "there are 8 tab-delimited fields"
    assert len(generated_track) == 2, "Header is valid, even if no measurements are present"


def test_rctrkadd_dict_and_timestamp():
    tk = RcTrack()
    test_year = 2025

    # reject adding offset-naive timestamp as the first point
    with pytest.raises(TypeError, match="offset-aware datetime"):
        tk.add_point_dict(
            {
                "DateTime": datetime(test_year, 1, 1, 0, 0, 0),
                "Latitude": 0.0,
                "Longitude": 0.0,
                "Accuracy": 1.0,
                "DoseRate": 1.0,
                "CountRate": 1.0,
            }
        )

    # this time with tzinfo
    tk.add_point_dict(
        {
            "DateTime": datetime(test_year, 1, 1, 0, 0, 0, tzinfo=UTC),
            "Latitude": 0.0,
            "Longitude": 0.0,
            "Accuracy": 1.0,
            "DoseRate": 1.0,
            "CountRate": 1.0,
        }
    )
    assert tk.timestamp.year == test_year

    # try add a second point, also without tzinfo
    with pytest.raises(TypeError, match="offset-aware datetime"):
        tk.add_point_dict(
            {
                "DateTime": datetime(test_year - 1, 1, 1, 0, 0, 0),
                "Latitude": 0.0,
                "Longitude": 0.0,
                "Accuracy": 1.0,
                "DoseRate": 1.0,
                "CountRate": 1.0,
            }
        )

    # add an old point with tzinfo, check that timestamp is correctly updated
    tk.add_point_dict(
        {
            "DateTime": _BEGINNING_OF_TIME,
            "Latitude": 0.0,
            "Longitude": 0.0,
            "Accuracy": 1.0,
            "DoseRate": 1.0,
            "CountRate": 1.0,
        }
    )
    assert tk.timestamp == _BEGINNING_OF_TIME

    # add a point after the oldest point, ensure that timestamp is preserved
    tk.add_point_dict(
        {
            "DateTime": _BEGINNING_OF_TIME.replace(year=test_year - 1),
            "Latitude": 0.0,
            "Longitude": 0.0,
            "Accuracy": 1.0,
            "DoseRate": 1.0,
            "CountRate": 1.0,
        }
    )
    assert tk.timestamp == _BEGINNING_OF_TIME
