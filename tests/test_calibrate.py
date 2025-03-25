#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import json
import os
from argparse import Namespace
from tempfile import mkstemp

import pytest

import calibrate


def test_argparse_fail(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, "-o", "-1"])
    with pytest.raises(SystemExit):
        calibrate.get_args()


def test_argparse_fail2(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, "-o", "2.5"])
    with pytest.raises(SystemExit):
        calibrate.get_args()


def test_argparse(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, "-o", "2"])
    parsed_args = calibrate.get_args()
    assert parsed_args.order == 2


def test_load_calibration_devnull_fail():
    args = Namespace(cal_file="/dev/null")
    with pytest.raises(json.decoder.JSONDecodeError):
        calibrate.load_calibration(args)


def test_cal_file_unconfigured_fail():
    fd, cal_file = mkstemp(prefix="pytest")
    os.close(fd)
    args = Namespace(cal_file=cal_file)
    with pytest.raises(SystemExit):
        # template_calibration exits
        calibrate.template_calibration(args=args)

    with pytest.raises(TypeError):
        calibrate.load_calibration(args)

    os.unlink(cal_file)


def test_cal_file(monkeypatch):
    fd, cal_file = mkstemp(prefix="pytest")
    os.close(fd)
    args = Namespace(cal_file=cal_file, order=2, precision=8, zero_start=True)
    with pytest.raises(SystemExit):
        # template_calibration exits
        calibrate.template_calibration(args=args)

    s1 = os.path.getsize(cal_file)
    assert s1 > 1024

    with open(cal_file) as fd:
        cal = json.load(fd)

    u = "unobtainium"
    assert u in cal
    cal.pop(u)
    assert u not in cal

    with open(cal_file, "w") as fd:
        json.dump(cal, fd)
    s2 = os.path.getsize(cal_file)
    assert s2 < s1

    cal = calibrate.load_calibration(args)

    chan, energy = zip(*cal)
    expected_fit = [1.11173792, 2.77390428, 3.66e-06]
    expected_rsq = 1.0

    pf = calibrate.make_fit(chan, energy, args)
    assert calibrate.make_fit(chan, energy, args) == expected_fit

    rsq = calibrate.rsquared(chan, energy, pf)
    assert pytest.approx(rsq, rel=1e-5) == expected_rsq  #

    monkeypatch.setattr("sys.argv", [__file__, "-f", cal_file])
    assert calibrate.main() is None

    os.unlink(cal_file)


def test_main_file(monkeypatch):
    with pytest.raises(SystemExit):
        monkeypatch.setattr("sys.argv", [__file__, "-f", "/dev/null"])
        calibrate.main()
    with pytest.raises(SystemExit):
        monkeypatch.setattr("sys.argv", [__file__, "-f", "./nonexistent"])
        calibrate.main()
