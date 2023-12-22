#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import sys
import datetime
from radiacode.types import Spectrum
from n42convert import load_radiacode_spectrum
from rcutils import get_dose_from_spectrum
from os.path import dirname, join as pathjoin
import radiacode_poll
import unittest
from unittest.mock import patch
from io import StringIO

# Approximately when I started writing this; used to give a stable start time
test_epoch = datetime.datetime(2023, 10, 13, 13, 13, 13)
# gonna need to fake time of day for sleep and stuff.
fake_clock: float = test_epoch.timestamp()
testdir = pathjoin(dirname(__file__), "data")


class MockRadiaCode:
    fw_sig = 'Signature: 57353F42, FileName="rc-102.bin", IdString="RadiaCode RC-102"'
    fw_ver = "Boot version: 4.0 Feb  6 2023 15:49:14 | Target version: 4.7 Sep 21 2023 10:56:58\x00"
    hsn = "0035001C-464B5009-20393153"
    conn_time = test_epoch

    th_data = load_radiacode_spectrum(pathjoin(testdir, "data_th232_plus_background.xml"))
    sn = th_data["foreground"]["device_serial_number"]
    a0 = th_data["foreground"]["calibration_values"][0]
    a1 = th_data["foreground"]["calibration_values"][1]
    a2 = th_data["foreground"]["calibration_values"][2]
    real_time = 0

    th232_duration = th_data["foreground"]["duration"]
    th232 = th_data["foreground"]["spectrum"]
    th232_cps = sum(th232) / th232_duration
    counts = [0] * len(th232)

    def __init__(self, mac=None):
        pass

    def fw_signature(self):
        return self.fw_sig

    def fw_version(self):
        return self.fw_ver

    def hw_serial_number(self):
        return self.hsn

    def serial_number(self):
        return self.sn

    def base_time(self):
        return self.conn_time

    def spectrum(self):
        self.real_time += 10
        m = self.real_time / self.th232_duration
        self.counts = [int(c * m) for c in self.th232]
        return Spectrum(
            duration=datetime.timedelta(seconds=self.real_time), a0=self.a0, a1=self.a1, a2=self.a2, counts=self.counts
        )

    def spectrum_reset(self):
        self.real_time = 0
        self.counts = [0] * len(self.th232)

    def dose_reset(self):
        pass


def fake_sleep(seconds: float):
    global fake_clock
    fake_clock += seconds


def fake_time_time():
    return fake_clock


class TestRadiaCodePoll(unittest.TestCase):
    test_timeofday = fake_time_time()

    def test_get_args(self):
        with patch("sys.argv", [__file__, "-u", "--accumulate-dose", "10"]):
            args = radiacode_poll.get_args()
            self.assertTrue(args.url)

        with patch("sys.argv", [__file__, "-u", "--accumulate-dose", "0"]), self.assertRaises(SystemExit):
            args = radiacode_poll.get_args()
            self.assertTrue(args.url)

    def test_format_spectrum(self):
        dev = MockRadiaCode()

        devid = radiacode_poll.get_device_id(dev)
        self.assertIn("RC-102", devid["sernum"])

        instrument_info = radiacode_poll.make_instrument_info(devid)
        self.assertIn("python-radiacode", instrument_info)

        sp = dev.spectrum()
        formatted = radiacode_poll.format_spectrum(hw_num=devid["sernum"], res=sp)
        self.assertIn("EnergyCalibration", formatted[0])

    def test_accumulated_dose(self):
        dev = MockRadiaCode()
        s = Spectrum(
            duration=datetime.timedelta(seconds=dev.th232_duration),
            a0=dev.a0,
            a1=dev.a1,
            a2=dev.a2,
            counts=dev.th232,
        )
        self.assertAlmostEqual(303.20, get_dose_from_spectrum(s.counts, s.a0, s.a1, s.a2), delta=0.01)

    def test_main(self):
        with patch("sys.stdout", new_callable=StringIO):
            with patch("radiacode.RadiaCode", MockRadiaCode):
                with patch("sys.argv", [__file__, "-u", "--reset-spectrum", "--reset-dose"]):
                    radiacode_poll.main()
        expected = "RADDATA://G0/0400/6BFH"
        self.assertEqual("RADDATA://G0/0400/6BFH", sys.stdout.read(len(expected)))
