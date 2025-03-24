#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

from os.path import dirname
from os.path import join as pathjoin

import pytest

from radiacode_tools.rc_files import RcTrack
from radiacode_tools.rc_utils import _BEGINNING_OF_TIME

testdir = pathjoin(dirname(__file__), "data")


def test_rctrk():
    tk = RcTrack()
    tk.add_point(dt=_BEGINNING_OF_TIME, latitude=0.0, longitude=0.0, accuracy=1.0, dose_rate=1.0, count_rate=1.0)
    assert str(tk)
    assert len(tk.points) == 1
    tk.write_file("/dev/null")


def test_rctrk_dict_roundtrip():
    tk1 = RcTrack(pathjoin(testdir, "walk.rctrk"))
    tk2 = RcTrack()

    tk2.from_dict(tk1.as_dict())
    assert len(tk1.points) == len(tk2.points)
    assert tk1.points[0].datetime.timestamp() == tk2.points[0].datetime.timestamp()


def test_rctrk_bogus():
    tk = RcTrack()
    with pytest.raises(ValueError):
        tk.from_dict(dict())
