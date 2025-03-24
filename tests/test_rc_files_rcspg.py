#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

from os.path import dirname
from os.path import join as pathjoin

import pytest

from radiacode_tools.rc_files import RcSpectrogram

testdir = pathjoin(dirname(__file__), "data")


@pytest.mark.slow
def test_rcspg():
    spg = RcSpectrogram(pathjoin(testdir, "K40.rcspg"))
    assert spg.name
    assert str(spg)
    spg.write_file("/dev/null")

    spg2 = RcSpectrogram()
    spg2.add_calibration(spg.calibration)
    # spg2.historical_spectrum = spg.historical_spectrum
    _ = [spg2.add_point(timestamp=s.datetime, counts=s.counts) for s in spg.samples if len(s.counts) == spg.channels]
    assert len(spg2.samples) > len(spg.samples) // 2
