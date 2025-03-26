#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import datetime
import sys
from io import StringIO
from os.path import dirname
from os.path import join as pathjoin
from signal import SIGALRM, alarm, signal

import pytest
from radiacode.types import Spectrum

import radiacode_poll
from radiacode_tools.rc_utils import get_dose_from_spectrum

# Approximately when I started writing this; used to give a stable start time
test_epoch = datetime.datetime(2023, 10, 13, 13, 13, 13)
# gonna need to fake time of day for sleep and stuff.
fake_clock: float = test_epoch.timestamp()
testdir = pathjoin(dirname(__file__), "data")

from .mock_radiacode import MockRadiaCode


def fake_sleep(seconds: float):
    global fake_clock
    fake_clock += seconds


def fake_time_time():
    return fake_clock


test_timeofday = fake_time_time()


def test_get_args(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, "-u", "--accumulate-dose", "10"])
    args = radiacode_poll.get_args()
    assert args.url is True

    monkeypatch.setattr("sys.argv", [__file__, "-u", "--accumulate-dose", "0"])
    with pytest.raises(SystemExit):
        args = radiacode_poll.get_args()


def test_accumulated_dose():
    dev = MockRadiaCode()
    s = Spectrum(
        duration=datetime.timedelta(seconds=dev.th232_duration),
        a0=dev.a0,
        a1=dev.a1,
        a2=dev.a2,
        counts=dev.th232,
    )
    assert pytest.approx(303.20, abs=1e-2) == get_dose_from_spectrum(s.counts, s.a0, s.a1, s.a2)


@pytest.mark.slow
def test_wait():
    def catch_sigalrm(*unused):
        raise KeyboardInterrupt

    signal(SIGALRM, catch_sigalrm)
    alarm(2)
    assert radiacode_poll.wait_for_keyboard_interrupt() is None


def test_main(monkeypatch):
    monkeypatch.setattr(sys, "stdout", StringIO())
    monkeypatch.setattr("radiacode.RadiaCode", MockRadiaCode)
    monkeypatch.setattr("sys.argv", [__file__, "-u", "--reset-spectrum", "--reset-dose"])
    assert radiacode_poll.main() is None
    expected = "RADDATA://G0/0400/6BFH"
    assert expected in sys.stdout.getvalue()
