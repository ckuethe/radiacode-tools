#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import datetime
from os.path import dirname
from os.path import join as pathjoin

from radiacode.types import DoseRateDB, Event, RareData, RawData, RealTimeData, Spectrum

from radiacode_tools.rc_files import RcSpectrum

# Approximately when I started writing this; used to give a stable start time
test_epoch = datetime.datetime(2023, 10, 13, 13, 13, 13)
# gonna need to fake time of day for sleep and stuff.
fake_clock: float = test_epoch.timestamp()
testdir = pathjoin(dirname(__file__), "data")


class MockRadiaCode:
    def __init__(self, serial_number=None, mac=None):
        self.fw_sig = 'Signature: 57353F42, FileName="rc-102.bin", IdString="RadiaCode RC-102"'
        self.fw_ver = ((4, 0, "Feb  6 2023 15:49:14"), (4, 9, "Jan 25 2024 14:49:00"))
        self.hsn = "0035001C-464B5009-20393153"
        self.conn_time = test_epoch

        sp = RcSpectrum(pathjoin(testdir, "data_th232_plus_background.xml"))
        self.sn = serial_number if serial_number else sp.fg_spectrum.serial_number
        c = sp.fg_spectrum.calibration
        self.a0, self.a1, self.a2 = c.a0, c.a1, c.a2
        self.real_time = 0

        self.th232_duration = sp.fg_spectrum.duration.total_seconds()
        self.th232 = sp.fg_spectrum.counts
        self.th232_cps = sum(self.th232) / self.th232_duration
        self.counts = [0] * len(self.th232)

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

    def spectrum_accum(self):
        return Spectrum(duration=datetime.timedelta(0), a0=self.a0, a1=self.a1, a2=self.a2, counts=[0] * 1024)

    def spectrum_reset(self):
        self.real_time = 0
        self.counts = [0] * len(self.th232)

    def dose_reset(self):
        pass

    def set_device_on(self, on: bool):
        pass

    def set_local_time(self, dt: datetime.datetime):
        pass

    def data_buf(self):
        now = test_epoch + datetime.timedelta(seconds=self.real_time)
        records = [
            Event(
                dt=now,
                event=0,
                event_param1=0,
                flags=0,
            ),
            RareData(
                dt=now,
                duration=2969738,
                dose=9.5740e0 - 3,
                temperature=33.0,
                charge_level=75.47,
                flags=0x5040,
            ),
            DoseRateDB(
                dt=now,
                count=1502,
                count_rate=15.646,
                dose_rate=9.1911e-5,
                dose_rate_err=12.7,
                flags=0x5001,
            ),
            RealTimeData(
                dt=test_epoch,
                count_rate=15.764,
                count_rate_err=6.2,
                dose_rate=9.8098e-5,
                dose_rate_err=15.0,
                flags=0x4041,
                real_time_flags=0,
            ),
            RawData(
                dt=now,
                count_rate=18.0,
                dose_rate=1.0049e-4,
            ),
        ]
        return records
