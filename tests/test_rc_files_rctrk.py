#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

from io import StringIO
from json import dumps as jdumps
from os.path import dirname
from os.path import join as pathjoin

import pytest

from radiacode_tools.rc_files import RcTrack
from radiacode_tools.rc_utils import _BEGINNING_OF_TIME

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
    assert jdumps(tk1.as_dict())


def test_rctrk_dict_roundtrip():
    tk1 = RcTrack(pathjoin(testdir, "walk.rctrk"))
    tk2 = RcTrack()

    tk2.from_dict(tk1.as_dict())
    assert len(tk1.points) == len(tk2.points)
    assert tk1.points[0].datetime.timestamp() == tk2.points[0].datetime.timestamp()


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
