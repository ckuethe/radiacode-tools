#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

from os.path import dirname
from os.path import join as pathjoin

import pytest

import deadtime

testdir = pathjoin(dirname(__file__), "data_deadtime")


f_a = pathjoin(testdir, "Ba133_Eu152", "Ba133_a.xml")
f_b = pathjoin(testdir, "Ba133_Eu152", "Eu152_b.xml")
f_ab = pathjoin(testdir, "Ba133_Eu152", "Ba133_a+Eu152_b.xml")
f_bg = pathjoin(testdir, "bg.xml")

# More work needs to be done to understand the behavior of the scintillator with varying
# fluxes. Dead time is nonlinear, but how non-linear? Does it depend on absorbed dose?
# These measurements used two 1uCi sources, 72mm away from the detector, on a granite
# surface.
r_Ba = 1849708 / 300
r_Ba_Eu = 2720349 / 300
r_bg = 16832 / 3903
r_Eu = 1075972 / 300
expected_dt_w_bg = 16.66e-6
expected_dt_no_bg = 16.75e-6
expected_lost_cps = 684
expected_loss_fraction = 0.07


def test_get_args(monkeypatch):
    "does get_args() work?"
    monkeypatch.setattr("sys.argv", [__file__, "-a", f_a, "-b", f_b, "-c", f_ab, "-g", f_bg])
    args = deadtime.get_args()
    assert args.first == f_a
    assert args.second == f_b
    assert args.combined == f_ab
    assert args.background == f_bg

    # Also check that file vs float input works
    rates = deadtime.load_spectra(args)
    # Right now, I don't care how much greater than zero
    assert rates["a"] > 0
    assert rates["b"] > 0
    assert rates["ab"] > 0
    assert rates["bg"] > 0


def test_get_args_nobg(monkeypatch):
    "does get_args() correctly handle no background?"
    monkeypatch.setattr("sys.argv", [__file__, "-a", f_a, "-b", f_b, "-c", f_ab])
    args = deadtime.get_args()
    assert args.first == f_a
    assert args.second == f_b
    assert args.combined == f_ab
    assert args.background is None


def test_get_args_numeric(monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        [__file__, "-a", f"{r_Ba}", "-b", f"{r_Eu}", "-c", f"{r_Ba_Eu}", "-g", f"{r_bg}"],
    )
    args = deadtime.get_args()
    assert pytest.approx(float(args.first), abs=1e-5) == r_Ba
    assert pytest.approx(float(args.second), abs=1e-5) == r_Eu
    assert pytest.approx(float(args.combined), abs=1e-5) == r_Ba_Eu
    assert pytest.approx(float(args.background), abs=1e-5) == r_bg

    count_rates = deadtime.load_spectra(args)
    dt = deadtime.compute_deadtime(**count_rates)
    assert pytest.approx(dt.dt_us, abs=1e-5) == expected_dt_w_bg


def test_get_args_numeric_nobg(monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        [__file__, "-a", f"{r_Ba}", "-b", f"{r_Eu}", "-c", f"{r_Ba_Eu}"],
    )
    args = deadtime.get_args()

    count_rates = deadtime.load_spectra(args)
    dt = deadtime.compute_deadtime(**count_rates)
    assert pytest.approx(dt.dt_us, abs=1e-5) == expected_dt_no_bg
    assert pytest.approx(dt.loss_fraction, abs=1e-3) == expected_loss_fraction
    assert pytest.approx(dt.lost_cps, abs=0.5) == expected_lost_cps


def test_get_args_fail(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, "-a", f_a, "-b", f_b, "-g", f_bg])
    with pytest.raises(SystemExit):
        deadtime.get_args()


def test_compute_deadtime_bg_fail():
    with pytest.raises(ValueError, match=".*Background cannot be negative") as cm:
        deadtime.compute_deadtime(a=100, b=100, ab=190, bg=-1)


def test_compute_deadtime_fg_fail():
    with pytest.raises(ValueError, match=".*Source counts must be greater than zero.*") as cm:
        deadtime.compute_deadtime(a=0, b=1, ab=1, bg=0)


def test_main(monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        [__file__, "-a", f"{r_Ba}", "-b", f"{r_Eu}", "-c", f"{r_Ba_Eu}", "-g", f"{r_bg}"],
    )
    assert deadtime.main() is None
