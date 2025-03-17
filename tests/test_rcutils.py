#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import datetime
import unittest

from radiacode_tools.rc_types import SpecData, Spectrum
from radiacode_tools.rc_utils import (
    UTC,
    DateTime2FileTime,
    FileTime2DateTime,
    UnixTime2FileTime,
    get_device_id,
    get_dose_from_spectrum,
    specdata_to_dict,
    stringify,
)

from .mock_radiacode import MockRadiaCode


class TestRadiaCodeUtils(unittest.TestCase):
    unix_time = datetime.datetime(2023, 12, 1, 8, 16, 11, tzinfo=UTC)
    file_time = 133458921710000000

    test_serial_number = "RC-102-112358"
    test_duration = 86400
    a = [-10, 2.5, 4.5e-4]
    channels = 1024

    def test_datetime_to_filetime(self):
        self.assertEqual(DateTime2FileTime(self.unix_time), self.file_time)

    def test_filetime_to_datetime(self):
        self.assertEqual(FileTime2DateTime(self.file_time), self.unix_time)

    def test_spectrum_dose(self):
        a = [-10, 3.0, 0]
        c = [100] * 1024
        usv = get_dose_from_spectrum(c, *a)
        self.assertAlmostEqual(usv, 5.5458, delta=1e-3)

    def test_stringify(self):
        testcases = [([], ""), ([0], "0"), ([0, 1, 2, 3], "0 1 2 3")]

        for t in testcases:
            self.assertEqual(stringify(t[0]), t[1])
            self.assertEqual(stringify(t[0], ","), t[1].replace(" ", ","))

    def test_get_device_info(self):
        dev = MockRadiaCode()
        devinfo = get_device_id(dev=dev)
        model = "RC-102"
        self.assertIn(model, devinfo["sernum"])
        self.assertEqual(model, devinfo["model"])

    def test_specdata_to_dict(self):
        t_counts = list(range(self.channels))

        sd_in = SpecData(
            time=self.unix_time.timestamp(),
            serial_number=self.test_serial_number,
            spectrum=Spectrum(datetime.timedelta(seconds=self.test_duration), *self.a, t_counts),
        )

        sd_out = specdata_to_dict(sd_in)
        self.assertEqual(self.test_serial_number, sd_out["serial_number"])
        self.assertEqual(self.unix_time.timestamp(), sd_out["timestamp"])
        self.assertEqual(sd_out["counts"][self.channels - 1], self.channels - 1)
        self.assertEqual(sd_out["duration"], self.test_duration)
