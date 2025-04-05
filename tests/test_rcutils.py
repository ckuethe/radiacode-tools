#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import datetime

import pytest

from radiacode_tools.rc_types import EnergyCalibration, SpecData, Spectrum
from radiacode_tools.rc_utils import (
    UTC,
    DateTime2FileTime,
    FileTime2DateTime,
    get_device_id,
    get_dose_from_spectrum,
    stringify,
)

from .mock_radiacode import MockRadiaCode

unix_time = datetime.datetime(2023, 12, 1, 8, 16, 11, tzinfo=UTC)
file_time = 133458921710000000

test_serial_number = "RC-102-112358"
test_duration = 86400
a = [-10, 2.5, 4.5e-4]
channels = 1024


def test_datetime_to_filetime():
    assert DateTime2FileTime(unix_time) == file_time


def test_filetime_to_datetime():
    assert FileTime2DateTime(file_time) == unix_time


def test_spectrum_dose():
    a = EnergyCalibration(a0=-10, a1=3.0, a2=0)
    c = [100] * 1024
    usv = get_dose_from_spectrum(c, a)
    assert pytest.approx(usv, abs=1e-3) == 5.5458


def test_stringify():
    testcases = [([], ""), ([0], "0"), ([0, 1, 2, 3], "0 1 2 3")]

    for t in testcases:
        assert stringify(t[0]) == t[1]
        assert stringify(t[0], ",") == t[1].replace(" ", ",")


def test_get_device_info():
    dev = MockRadiaCode()
    devinfo = get_device_id(dev=dev)
    model = "RC-102"
    assert model in devinfo.serial_number
    assert model == devinfo.model


def test_specdata_to_dict():
    t_counts = list(range(channels))

    sd_in = SpecData(
        dt=unix_time.timestamp(),
        serial_number=test_serial_number,
        spectrum=Spectrum(datetime.timedelta(seconds=test_duration), *a, t_counts),
    )

    sd_out = sd_in.as_dict()
    assert test_serial_number == sd_out["serial_number"]
    assert unix_time.timestamp() == sd_out["dt"]
    assert sd_out["spectrum"].counts[channels - 1] == channels - 1
    assert sd_out["spectrum"].duration == datetime.timedelta(seconds=test_duration)
