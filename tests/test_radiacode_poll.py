#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import datetime
import sys
from io import StringIO
from os.path import dirname
from os.path import join as pathjoin
from unittest.mock import patch

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


def test_get_args():
    with patch("sys.argv", [__file__, "-u", "--accumulate-dose", "10"]):
        args = radiacode_poll.get_args()
        assert args.url is True

    with patch("sys.argv", [__file__, "-u", "--accumulate-dose", "0"]), pytest.raises(SystemExit):
        args = radiacode_poll.get_args()
        assert args.url is True


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


def test_main():
    with patch("sys.stdout", new=StringIO()) as mock_stdout:
        with patch("radiacode.RadiaCode", MockRadiaCode):
            with patch("sys.argv", [__file__, "-u", "--reset-spectrum", "--reset-dose"]):
                assert radiacode_poll.main() is None
    expected = "RADDATA://G0/0400/6BFH"
    assert expected in mock_stdout.getvalue()
