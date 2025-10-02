#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import datetime
import sys
from argparse import Namespace
from os.path import dirname
from os.path import join as pathjoin
from time import monotonic
from time import sleep as real_sleep

import pytest

import rcrtlog

from .mock_radiacode import MockRadiaCode

# Approximately when I started writing this; used to give a stable start time
test_epoch = datetime.datetime(2023, 10, 13, 13, 13, 13)
# gonna need to fake time of day for sleep and stuff.
fake_clock: float = test_epoch.timestamp()
testdir = pathjoin(dirname(__file__), "data")
sn: str = "RC-100-000000"


# FIXME - make these a fixture that can be resued in all the unit tests
def fake_sleep(seconds: float) -> None:
    global fake_clock
    fake_clock += seconds
    real_sleep(0.05)


def fake_time_time() -> float:
    return fake_clock + monotonic()


test_timeofday: float = fake_time_time()


def test_get_args_help(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, "-h"])
    with pytest.raises(SystemExit):
        rcrtlog.get_args()


def test_get_args(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, "-b", "00:00:00:00:00:00", "-d", sn])
    with pytest.raises(SystemExit):
        rcrtlog.get_args()

    monkeypatch.setattr("sys.argv", [__file__, "--device", sn, "-jsqrx"])
    args: Namespace = rcrtlog.get_args()
    assert args.device == sn
    assert args.jsonlog
    assert args.stdout
    assert args.exit_after_sync
    assert args.no_rtdata
    assert args.raise_exceptions


def test_wait_for_rc_activity(monkeypatch):
    monkeypatch.setattr("time.sleep", fake_sleep)
    monkeypatch.setattr("time.time", fake_time_time)
    rc = MockRadiaCode()
    assert rcrtlog.wait_for_rc_activity(rc) is None

    with pytest.raises(TimeoutError):
        rcrtlog.wait_for_rc_activity(rc, -1)


def test_main(monkeypatch):
    monkeypatch.setattr("time.sleep", fake_sleep)
    monkeypatch.setattr("time.time", fake_time_time)
    monkeypatch.setattr("sys.argv", [__file__, "-q"])
    monkeypatch.setattr("radiacode.RadiaCode", MockRadiaCode)
    assert rcrtlog.main() is None
    assert "DoseRateDB" in sys.stdout.read()
