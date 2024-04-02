#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import datetime
import unittest
from argparse import Namespace
from collections import namedtuple
from unittest.mock import mock_open, patch

import rcmultispg
from rcmultispg import SpecData, Spectrum


class TestRadiaCodePoll(unittest.TestCase):
    unix_time = datetime.datetime(2023, 12, 1, 0, 16, 11)
    devs = ["RC-101-111111", "RC-102-222222", "RC-103-333333"]
    a = [-10, 2.5, 4.5e-4]
    channels = 1024

    def test_unix_time_to_filetime(self):
        ut = self.unix_time.timestamp()
        self.assertEqual(rcmultispg.UnixTime2FileTime(ut), 133458921710000000)

    def test_get_args(self):
        # arbitrary
        with patch(
            "sys.argv",
            [__file__, "-a", "-d", self.devs[0], "-d", self.devs[1], "-d", self.devs[2], "-i", "60"],
        ):
            args = rcmultispg.get_args()
            self.assertTrue(args.require_all)
            self.assertEqual(len(args.devs), 3)
            self.assertEqual(args.interval, 60)

        # deduplicate devices, clamp polling time
        with patch(
            "sys.argv",
            [__file__, "-d", self.devs[1], "-d", self.devs[2], "-d", self.devs[1], "-i", "0"],
        ):
            args = rcmultispg.get_args()
            self.assertFalse(args.require_all)
            self.assertEqual(len(args.devs), 2)
            self.assertEqual(args.interval, 0.5)

        # Reject negative times
        with patch("sys.argv", [__file__, "-i", "-10"]), self.assertRaises(SystemExit):
            args = rcmultispg.get_args()

    def test_get_radiacode_devices(self):
        FakeUsb = namedtuple("FakeUsb", ["serial_number"])

        with patch("usb.core.find", return_value=[FakeUsb(x) for x in self.devs]):
            devs = rcmultispg.find_radiacode_devices()
            self.assertEqual(devs, self.devs)

    def test_make_header(self):
        serial_number = self.devs[0]
        duration = 123456
        comment = "Can neither confirm nor deny that I was ever at chernobyl"

        hdr = rcmultispg.make_spectrogram_header(
            duration=duration,
            start_time=self.unix_time.timestamp(),
            serial_number=serial_number,
            comment=comment,
            channels=self.channels,
        )
        self.assertIn(f"Device serial: {serial_number}", hdr)
        self.assertIn(f"Accumulation time: {duration}", hdr)
        self.assertIn(f"Channels: {self.channels}", hdr)
        self.assertIn("Spectrogram: rcmulti-", hdr)  # unspecified name, default prefix
        self.assertIn(comment, hdr)

    def test_make_spectrum_line(self):
        s = Spectrum(datetime.timedelta(seconds=0x12345678), *self.a, [0] * self.channels)
        hdr = rcmultispg.make_spectrum_line(s)
        expected = "Spectrum: 78 56 34 12 00 00 20 c1 00 00 20 40 fa ed eb 39 00 00 00 00"
        self.assertIn(expected, hdr)

    def test_format_spectra(self):
        data = [
            # Total Dose
            SpecData(0, Spectrum(datetime.timedelta(0), *self.a, [0] * self.channels)),
            # Baseline at the start of the spectrogram
            SpecData(0, Spectrum(datetime.timedelta(0), *self.a, [0] * self.channels)),
        ]
        for i in range(5):
            tmp = [2**i] * 2**i
            tmp.extend([0] * self.channels)
            data.append(SpecData(i + 1, Spectrum(datetime.timedelta(seconds=i), *self.a, tmp[: self.channels])))

        res = rcmultispg.format_spectra(data).splitlines()
        want = [
            "116444736010000000 1 1".replace(" ", "\t"),
            "116444736020000000 1 1 2".replace(" ", "\t"),
            "116444736030000000 1 2 2 4 4".replace(" ", "\t"),
            "116444736040000000 1 4 4 4 4 8 8 8 8".replace(" ", "\t"),
            "116444736050000000 1 8 8 8 8 8 8 8 8 16 16 16 16 16 16 16 16".replace(" ", "\t"),
        ]

        for i in range(5):
            self.assertEqual(res[i], want[i])

    def test_save_data(self):
        data = [
            # Total Dose
            SpecData(0, Spectrum(datetime.timedelta(0), *self.a, [0] * self.channels)),
            # Baseline at the start of the spectrogram
            SpecData(0, Spectrum(datetime.timedelta(0), *self.a, [0] * self.channels)),
        ]
        for i in range(5):
            tmp = [2**i] * 2**i
            tmp.extend([0] * self.channels)
            data.append(SpecData(i + 1, Spectrum(datetime.timedelta(seconds=i), *self.a, tmp[: self.channels])))

        m = mock_open()
        with patch("builtins.open", m):
            rcmultispg.save_data(data=data, serial_number=self.devs[0], use_pickle=True)
        payload = "\t".join(
            [
                "Spectrogram: rcmulti-19700101000000-RC-101-111111",
                "Time: 1970-01-01 00:00:00",
                "Timestamp: 116444736000000000",
                "Accumulation time: 4",
                "Channels: 1024",
                "Device serial: RC-101-111111",
                "Flags: 1",
                "Comment: ",
            ]
        )

        # There's probably a better way to do this
        wr_calls = m.mock_calls
        # self.assertIsNone(wr_calls) # so I can throw an error to see the payloads
        wr_calls[2].assert_called_with(payload)

    def test_main_fails(self):
        FakeUsb = namedtuple("FakeUsb", ["serial_number"])

        with patch("sys.argv", [__file__, "-a", "-d", self.devs[0]]), patch(
            "usb.core.find", return_value=[FakeUsb(x) for x in self.devs[1:]]
        ), self.assertRaises(SystemExit):
            rcmultispg.main()

        with patch("sys.argv", [__file__, "-i", "1"]), patch("usb.core.find", return_value=[]), self.assertRaises(
            SystemExit
        ):
            rcmultispg.main()

    def test_rc_worker(self):
        args = Namespace(interval=1, prefix="foobar")
        rcmultispg.rc_worker(args, serial_number=self.devs[0], start_time=1234)
