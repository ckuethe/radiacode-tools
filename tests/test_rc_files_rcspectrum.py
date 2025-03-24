#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

from os.path import dirname
from os.path import join as pathjoin

import pytest

from radiacode_tools.rc_files import RcSpectrum

testdir = pathjoin(dirname(__file__), "data")


"Testing the Spectrum interface"


def test_rcspectrum():
    sp = RcSpectrum()
    assert str(sp)

    sp = RcSpectrum(pathjoin(testdir, "data_th232_plus_background.xml"))
    assert str(sp)
    assert sp.as_dict()
    # assert (sp.uuid())
    assert "2b06cd31-3519-2ca8-c6bb-698587cbe3d3" == sp.uuid()
    assert pytest.approx(153.2, abs=0.1) == sp.count_rate()
    assert pytest.approx(3.5, abs=0.1) == sp.count_rate(bg=True)
    sp.write_file("/dev/null")


def test_rcspectrum_invalid():
    with pytest.raises(ValueError):
        RcSpectrum(pathjoin(testdir, "data_invalid_spectrum.xml"))


def test_rcspectrum_incorrect_order():
    with pytest.raises(ValueError):
        RcSpectrum(pathjoin(testdir, "data_invalid_cal_incorrect_order.xml"))


def test_rcspectrum_inconsistent():
    with pytest.raises(ValueError):
        RcSpectrum(pathjoin(testdir, "data_invalid_cal_inconsistent_order.xml"))
