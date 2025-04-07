#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import datetime
from os.path import dirname
from os.path import join as pathjoin

from radiacode.types import Spectrum

from radiacode_tools.rc_files import RcSpectrum

# from rc_utils import get_device_id, get_dose_from_spectrum

# Approximately when I started writing this; used to give a stable start time
test_epoch = datetime.datetime(2023, 10, 13, 13, 13, 13)
# gonna need to fake time of day for sleep and stuff.
fake_clock: float = test_epoch.timestamp()
testdir = pathjoin(dirname(__file__), "data")


class MockRadiaCode:
    fw_sig = 'Signature: 57353F42, FileName="rc-102.bin", IdString="RadiaCode RC-102"'
    fw_ver = ((4, 0, "Feb  6 2023 15:49:14"), (4, 9, "Jan 25 2024 14:49:00"))
    hsn = "0035001C-464B5009-20393153"
    conn_time = test_epoch

    sp = RcSpectrum(pathjoin(testdir, "data_th232_plus_background.xml"))
    sn = sp.fg_spectrum.serial_number
    c = sp.fg_spectrum.calibration
    a0, a1, a2 = c.a0, c.a1, c.a2
    real_time = 0

    th232_duration = sp.fg_spectrum.duration.total_seconds()
    th232 = sp.fg_spectrum.counts
    th232_cps = sum(th232) / th232_duration
    counts = [0] * len(th232)

    def __init__(self, mac=None):
        print("Fake RadiaCode")
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
            duration=datetime.timedelta(seconds=self.real_time),
            a0=self.a0,
            a1=self.a1,
            a2=self.a2,
            counts=self.counts,
        )

    def spectrum_reset(self):
        self.real_time = 0
        self.counts = [0] * len(self.th232)

    def dose_reset(self):
        pass

    def set_device_on(self, on: bool):
        pass

    def set_local_time(self, dt: datetime.datetime):
        pass

    def data_buf(self) -> list:
        return list()
