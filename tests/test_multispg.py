#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import datetime
import signal
import threading
from argparse import Namespace
from collections import namedtuple
from json import loads as jloads

import pytest

import rcmultispg
from radiacode_tools.rc_types import GpsData, RtData, SpecData, Spectrum

from .mock_radiacode import MockRadiaCode

unix_time = datetime.datetime(2023, 12, 1, 0, 16, 11)
devs = ["RC-101-111111", "RC-102-222222", "RC-103-333333"]
a = [-10, 2.5, 4.5e-4]
channels = 1024


def _thread_shutdown_after(n=1):
    "shut down the threads by dropping the SHUTDOWN_OBJECt into CTRL_QUEUE after a delay"
    signal.signal(signal.SIGALRM, rcmultispg.handle_shutdown_signal)
    signal.alarm(n)


def _reset_queues():
    "Empty out the control and data queues"
    while rcmultispg.CTRL_QUEUE.empty() is False:
        rcmultispg.CTRL_QUEUE.get_nowait()
    while rcmultispg.DATA_QUEUE.empty() is False:
        rcmultispg.DATA_QUEUE.get_nowait()


def _create_metrics(sn):
    for gn in [f"dose_{sn}", f"dose_rate_{sn}", f"count_{sn}", f"count_rate_{sn}"]:
        if gn not in rcmultispg.ams._stats["gauge"]:
            rcmultispg.ams.gauge_create(gn)


def test_get_args(monkeypatch):
    # arbitrary
    monkeypatch.setattr(
        "sys.argv",
        [__file__, "-a", "-d", devs[0], "-d", devs[1], "-d", devs[2], "-i", "60"],
    )
    args = rcmultispg.get_args()
    assert args.require_all is True
    assert len(args.devs) == 3
    assert args.interval == 60

    # deduplicate devices, clamp polling time
    monkeypatch.setattr(
        "sys.argv",
        [__file__, "-d", devs[1], "-d", devs[2], "-d", devs[1], "-i", "0"],
    )
    args = rcmultispg.get_args()
    assert args.require_all is False
    assert len(args.devs) == 2
    assert args.interval == 0.5

    # Reject negative times
    monkeypatch.setattr("sys.argv", [__file__, "-i", "-10"])
    with pytest.raises(SystemExit):
        args = rcmultispg.get_args()


@pytest.mark.slow
def test_handle_shutdown():
    # it doesn't really matter what signal is triggers the shutdown signal
    # so use SIGALRM. Then I don't have to figure out which thread or process
    # this test runner is - alarm will deliver it to the right place. The only
    # drawback is that it'll take up to one second to deliver.
    _reset_queues()
    assert rcmultispg.CTRL_QUEUE.qsize() == 0
    assert rcmultispg.DATA_QUEUE.qsize() == 0
    _thread_shutdown_after()

    # ,get() is blocking so these will just wait until the signal handler
    # runs to put SHUTDOWN_OBJECT in the queues. It's an object that can
    # compared with "is". Using the blocking call means I don't have to
    # busy-wait or sleep
    assert rcmultispg.DATA_QUEUE.get() is rcmultispg.SHUTDOWN_OBJECT
    assert rcmultispg.CTRL_QUEUE.get() is rcmultispg.SHUTDOWN_OBJECT
    _reset_queues()


@pytest.mark.slow
def test_tbar():
    # tbar is a synchronizaton primitive I use to ensure that all device readers
    # have connected and are ready, which allows synchronized measurements.
    # Ensure that an exception is raised if time expires before everyone
    # checks in
    with pytest.raises(threading.BrokenBarrierError):
        rcmultispg.tbar(1)

    # But if everyone does check in on time, then proceed
    rcmultispg.THREAD_BARRIER = threading.Barrier(1)
    assert rcmultispg.tbar() is None


def test_get_radiacode_devices(monkeypatch):
    FakeUsb = namedtuple("FakeUsb", ["serial_number"])

    monkeypatch.setattr("usb.core.find", lambda idVendor, idProduct, find_all: [FakeUsb(x) for x in devs])
    found_devs = rcmultispg.find_radiacode_devices()
    assert devs == found_devs


@pytest.mark.slow
def test_log_worker(capfd):
    args = Namespace(stdout=True, devs=[devs[0]])
    _reset_queues()
    t = threading.Thread(target=rcmultispg.log_worker, args=(args,))
    t.start()
    monotime = 1.7e9
    rcmultispg.DATA_QUEUE.put(
        RtData(
            monotime=monotime,
            dt=unix_time,
            serial_number=devs[0],
            type="RareData",
            charge_level=42,
            temperature=23.45,
        )
    )
    rcmultispg.DATA_QUEUE.put(
        SpecData(
            monotime=monotime,
            dt=unix_time,
            serial_number=devs[0],
            spectrum=Spectrum(duration=1, a0=1, a1=2, a2=3, counts=[256] * 1024),
        )
    )
    rcmultispg.DATA_QUEUE.put(GpsData(monotime=monotime, payload=dict(gnss=False)))
    rcmultispg.DATA_QUEUE.put(None)
    rcmultispg.DATA_QUEUE.put(rcmultispg.SHUTDOWN_OBJECT)
    rcmultispg.CTRL_QUEUE.put(rcmultispg.SHUTDOWN_OBJECT)
    t.join(1)

    captured = capfd.readouterr()
    assert "ignored None" in captured.err
    assert "log_worker" in captured.err
    assert "SHUTDOWN_OBJECT" in captured.out
    lines = captured.out.splitlines()
    for line in lines:
        if not line.startswith("{"):
            continue
        msg = jloads(line.replace("NaN", "-1"))
        assert msg["monotime"] == monotime
        assert msg["_dataclass"] is True
        if msg["_type"] == "GpsData":
            assert msg["payload"]["gnss"] is False
        elif msg["_type"] == "SpecData":
            assert msg["serial_number"] == devs[0]
            assert len(msg["spectrum"]["counts"]) == 1024
        elif msg["_type"] == "RtData":
            assert msg["serial_number"] == devs[0]
            assert msg["charge_level"] == 42
            assert msg["temperature"] == 23.45


@pytest.mark.slow
def test_create_threads():
    args = Namespace(devs=devs, stdout=True, gpsd={"host": "localhost", "port": 1, "device": None})
    _reset_queues()
    rcmultispg.ams = rcmultispg.AppMetrics(stub=True)

    # do it!
    nthreads, threadz = rcmultispg.create_threads(args)

    # log worker should always exist
    assert nthreads == 2 + 2 * len(devs)
    assert threadz[0].name == "log-worker"

    # it's not important for this test that the gps thread actually connects to gpsd.
    assert threadz[0].is_alive() == True
    assert threadz[1].name == "gps-worker"

    # and we're not even going to start the poller threads
    for i, d in enumerate(devs):
        assert threadz[i + 2].name == f"poller-worker-{d}"
        assert threadz[i + 2].is_alive() == False

    # Nicely shut down the two running threads
    rcmultispg.CTRL_QUEUE.put(rcmultispg.SHUTDOWN_OBJECT)
    rcmultispg.DATA_QUEUE.put(rcmultispg.SHUTDOWN_OBJECT)
    [threadz[t].join(1) for _ in range(4) for t in range(2)]

    assert threadz[0].is_alive() is False
    assert threadz[1].is_alive() is False


def test_main_fails(monkeypatch):
    FakeUsb = namedtuple("FakeUsb", ["serial_number"])

    monkeypatch.setattr("sys.argv", [__file__, "-a", "-d", devs[0]])
    monkeypatch.setattr("usb.core.find", lambda: [FakeUsb(x) for x in devs[1:]])
    with pytest.raises(SystemExit):
        rcmultispg.main()

    monkeypatch.setattr("sys.argv", [__file__, "-i", "1"])
    monkeypatch.setattr("usb.core.find", lambda: [])
    with pytest.raises(SystemExit):
        rcmultispg.main()


@pytest.mark.slow
def test_rc_worker_failed(capsys):
    args = Namespace(interval=1, prefix="foobar")
    rcmultispg.ams = rcmultispg.AppMetrics(stub=True)
    sn = devs[0]
    assert rcmultispg.rc_worker(args, serial_number=sn) is False
    assert f"{devs[0]} failed to connect" in capsys.readouterr().err


@pytest.mark.slow
def test_rc_worker(capsys, monkeypatch):
    sn = devs[0]
    args = Namespace(interval=1, prefix="foobar", devs=[sn], reset_spectrum=False, reset_dose=False, poweroff=False)
    monkeypatch.setattr(rcmultispg, "RadiaCode", MockRadiaCode)
    rcmultispg.THREAD_BARRIER = rcmultispg.Barrier(1)
    rcmultispg.ams = rcmultispg.AppMetrics(stub=True)

    _reset_queues()
    _thread_shutdown_after()
    assert rcmultispg.rc_worker(args, serial_number=sn) is True
    assert f"{devs[0]} Connect" in capsys.readouterr().err


@pytest.mark.slow
def test_rc_rtdata_worker(capsys):
    dev = MockRadiaCode()
    sn = devs[0]
    dev.serial_number = sn
    rcmultispg.RC_LOCKS[sn] = threading.Lock()
    rcmultispg.ams = rcmultispg.AppMetrics(stub=True)

    _reset_queues()
    _create_metrics(sn)
    _thread_shutdown_after()

    assert rcmultispg.rtdata_worker(dev, serial_number=sn) is None
    o, e = capsys.readouterr()
    assert f"rtdata_worker for {sn}" in e
