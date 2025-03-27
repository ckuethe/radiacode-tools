#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

from json import dumps as jdumps
from os.path import dirname
from os.path import join as pathjoin

import pytest

from radiacode_tools.rc_files import RcSpectrum

testdir = pathjoin(dirname(__file__), "data")


"Testing the Spectrum interface"


def test_rcspectrum():
    "Basic operation: can we read and write a spectrum?"
    sp = RcSpectrum()
    assert str(sp)

    sp = RcSpectrum(pathjoin(testdir, "data_th232_plus_background.xml"))
    assert 36 == len(sp.uuid())
    assert pytest.approx(153.2, abs=0.1) == sp.count_rate()
    assert pytest.approx(3.5, abs=0.1) == sp.count_rate(bg=True)
    sp.write_file("/dev/null")


def test_rcspectrum_no_bg():
    "Like the previous, but this one has no background layer"
    sp = RcSpectrum(pathjoin(testdir, "data_th232_plus_background.xml"))
    sp.bg_spectrum = None
    assert pytest.approx(153.2, abs=0.1) == sp.count_rate()
    with pytest.raises(ValueError, match="bg_spectrum is undefined"):
        sp.count_rate(bg=True)


def test_rcspectrum_dict_can_jsonify():
    "check that all elements of the RcSpectrum can be encoded as basic JSON types"
    sp = RcSpectrum(pathjoin(testdir, "data_th232_plus_background.xml"))
    jd = jdumps(sp.as_dict())
    assert sp.fg_spectrum.spectrum_name in jd


def test_rcspectrum_dict_load():
    sp = RcSpectrum(pathjoin(testdir, "data_th232_plus_background.xml"))
    dd = sp.as_dict()

    # Can we round-trip?
    sp2 = RcSpectrum()
    sp2.from_dict(dd)
    assert sp.fg_spectrum == sp2.fg_spectrum
    assert sp.bg_spectrum == sp2.bg_spectrum

    # Mess up the number of channels
    dd["fg"]["channels"] = 0
    with pytest.raises(ValueError, match="Inconsistent channel count"):
        sp2.make_layer_from_dict(dd["fg"])

    # Mess up the channel counts
    dd["bg"]["channels"] = [0]
    with pytest.raises(ValueError, match="Inconsistent channel count"):
        sp2.make_layer_from_dict(dd["bg"])


def test_rcspectrum_invalid():
    with pytest.raises(ValueError):
        RcSpectrum(pathjoin(testdir, "data_invalid_spectrum.xml"))


def test_rcspectrum_incorrect_order():
    with pytest.raises(ValueError):
        RcSpectrum(pathjoin(testdir, "data_invalid_cal_incorrect_order.xml"))


def test_rcspectrum_inconsistent():
    with pytest.raises(ValueError):
        RcSpectrum(pathjoin(testdir, "data_invalid_cal_inconsistent_order.xml"))
