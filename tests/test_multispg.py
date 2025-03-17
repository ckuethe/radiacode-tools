#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import datetime
import unittest
from argparse import Namespace
from collections import namedtuple
from unittest.mock import patch

import rcmultispg


class TestMultispg(unittest.TestCase):
    unix_time = datetime.datetime(2023, 12, 1, 0, 16, 11)
    devs = ["RC-101-111111", "RC-102-222222", "RC-103-333333"]
    a = [-10, 2.5, 4.5e-4]
    channels = 1024

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

    # def test_save_data(self):
    #     data = [
    #         # Total Dose
    #         SpecData(0, self.devs[0], Spectrum(datetime.timedelta(0), *self.a, [0] * self.channels)),
    #         # Baseline at the start of the spectrogram
    #         SpecData(0, self.devs[0], Spectrum(datetime.timedelta(0), *self.a, [0] * self.channels)),
    #     ]
    #     for i in range(5):
    #         tmp = [2**i] * 2**i
    #         tmp.extend([0] * self.channels)
    #         data.append(
    #             SpecData(i + 1, self.devs[0], Spectrum(datetime.timedelta(seconds=i), *self.a, tmp[: self.channels]))
    #         )

    #     m = mock_open()
    #     with patch("builtins.open", m):
    #         # rcspg_save_spectrogram_file(data=data, serial_number=self.devs[0])
    #         pass
    #     payload = "\t".join(
    #         [
    #             "Spectrogram: rcmulti-19700101000000-RC-101-111111",
    #             "Time: 1970-01-01 00:00:00",
    #             "Timestamp: 116444736000000000",
    #             "Accumulation time: 4",
    #             "Channels: 1024",
    #             "Device serial: RC-101-111111",
    #             "Flags: 1",
    #             "Comment: ",
    #         ]
    #     )

    #     # There's probably a better way to do this
    #     wr_calls = m.mock_calls
    #     self.assertFalse(wr_calls)  # so I can throw an error to see the payloads
    #     #self.assertIsNone(wr_calls)  # so I can throw an error to see the payloads
    #     # wr_calls[2].assert_called_with(payload)

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
        rcmultispg.rc_worker(args, serial_number=self.devs[0])
