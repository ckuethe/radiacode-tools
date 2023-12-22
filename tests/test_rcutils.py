#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import datetime
import unittest
import rcutils


class TestRadiaCodeUtils(unittest.TestCase):
    unix_time = datetime.datetime(2023, 12, 1, 0, 16, 11)
    file_time = 133458921710000000

    def test_datetime_to_filetime(self):
        self.assertEqual(rcutils.DateTime2FileTime(self.unix_time), self.file_time)

    def test_filetime_to_datetime(self):
        self.assertEqual(rcutils.FileTime2DateTime(self.file_time), self.unix_time)

    def test_spectrum_dose(self):
        a = [-10, 3.0, 0]
        c = [100] * 1024
        usv = rcutils.get_dose_from_spectrum(c, *a)
        self.assertAlmostEqual(usv, 5.5458, delta=1e-3)

    def test_stringify(self):
        testcases = [([], ""), ([0], "0"), ([0, 1, 2, 3], "0 1 2 3")]

        for t in testcases:
            self.assertEqual(rcutils.stringify(t[0]), t[1])
            self.assertEqual(rcutils.stringify(t[0], ","), t[1].replace(" ", ","))
