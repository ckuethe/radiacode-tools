#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import datetime
import unittest

from rcutils import (
    DateTime2FileTime,
    FileTime2DateTime,
    SpecData,
    Spectrum,
    get_device_id,
    get_dose_from_spectrum,
    rcspg_format_spectra,
    rcspg_make_header,
    rcspg_make_spectrum_line,
    specdata_to_dict,
    stringify,
)

from .test_radiacode_poll import MockRadiaCode


class TestRadiaCodeUtils(unittest.TestCase):
    unix_time = datetime.datetime(2023, 12, 1, 0, 16, 11)
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
        self.assertIn("RC-102", devinfo["sernum"])

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

    def test_rcspg_make_header(self):
        name = "unit_test"
        comment = "all your base are belong to us"
        hdr = rcspg_make_header(
            duration=self.test_duration,
            serial_number=self.test_serial_number,
            start_time=self.unix_time.timestamp(),
            name=name,
            comment=comment,
        )

        self.assertIn(f"Spectrogram: {name}", hdr)
        self.assertIn(f"Device serial: {self.test_serial_number}", hdr)
        self.assertIn(f"Comment: {comment}", hdr)

    def test_make_spectrum_line(self):
        s = Spectrum(datetime.timedelta(seconds=0x12345678), *self.a, [0] * self.channels)
        hdr = rcspg_make_spectrum_line(s)
        expected = "Spectrum: 78 56 34 12 00 00 20 c1 00 00 20 40 fa ed eb 39 00 00 00 00"
        self.assertIn(expected, hdr)

    def test_format_spectra(self):
        data = [
            # Total Dose
            SpecData(0, self.test_serial_number, Spectrum(datetime.timedelta(0), *self.a, [0] * self.channels)),
            # Baseline at the start of the spectrogram
            SpecData(0, self.test_serial_number, Spectrum(datetime.timedelta(0), *self.a, [0] * self.channels)),
        ]
        for i in range(5):
            tmp = [2**i] * 2**i
            tmp.extend([0] * self.channels)
            data.append(
                SpecData(
                    i + 1,
                    self.test_serial_number,
                    Spectrum(datetime.timedelta(seconds=i), *self.a, tmp[: self.channels]),
                )
            )

        res = rcspg_format_spectra(data).splitlines()
        want = [
            "116444736010000000 1 1".replace(" ", "\t"),
            "116444736020000000 1 1 2".replace(" ", "\t"),
            "116444736030000000 1 2 2 4 4".replace(" ", "\t"),
            "116444736040000000 1 4 4 4 4 8 8 8 8".replace(" ", "\t"),
            "116444736050000000 1 8 8 8 8 8 8 8 8 16 16 16 16 16 16 16 16".replace(" ", "\t"),
        ]

        for i in range(5):
            self.assertEqual(res[i], want[i])
