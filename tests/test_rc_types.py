#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

from datetime import timedelta

import pytest

from radiacode_tools.rc_types import (
    EnergyCalibration,
    GeoBox,
    GeoCircle,
    GeoPoint,
    GpsData,
    RangeFinder,
    RcHwInfo,
    RtData,
    SGHeader,
    SpecData,
    SpecEnergy,
    SpectrogramPoint,
    Spectrum,
    SpectrumLayer,
    TimeRange,
    TrackPoint,
)
from radiacode_tools.rc_utils import _BEGINNING_OF_TIME, _THE_END_OF_DAYS


def test_rangefinder():
    l = [42, 65536, 0o105, 0xFF, -1, 0]
    rf = RangeFinder()
    rf.add(l)
    assert rf.get() == (min(l), max(l))
    assert str(max(l)) in str(rf)
    assert rf.__repr__() is None


# Rudimentary dataclass encoder tests
def test_EnergyCalibration():
    x = EnergyCalibration(a0=3, a1=2, a2=1)
    d = x.as_dict()
    j = x.json()
    assert d["_dataclass"] is True
    assert d["_type"] == x.__class__.__name__
    assert "_dataclass" in j
    assert x.__class__.__name__ in j
    assert x.values() == (3, 2, 1)


def test_GeoBox():
    x = GeoBox(p1=GeoPoint(latitude=0, longitude=1), p2=GeoPoint(latitude=2, longitude=3))
    d = x.as_dict()
    j = x.json()
    assert d["_dataclass"] is True
    assert d["_type"] == x.__class__.__name__
    assert "_dataclass" in j
    assert x.__class__.__name__ in j
    assert len(x.values()) == 2


def test_GeoCircle():
    x = GeoCircle(point=GeoPoint(latitude=0, longitude=1), radius=2)
    d = x.as_dict()
    j = x.json()
    assert d["_dataclass"] is True
    assert d["_type"] == x.__class__.__name__
    assert "_dataclass" in j
    assert x.__class__.__name__ in j
    assert len(x.values()) == 2


def test_GeoPoint():
    x = GeoPoint(latitude=0, longitude=1)
    d = x.as_dict()
    j = x.json()
    assert d["_dataclass"] is True
    assert d["_type"] == x.__class__.__name__
    assert "_dataclass" in j
    assert x.__class__.__name__ in j
    assert x.values() == (0, 1)


def test_RcHwInfo():
    sentinel = "c0ffee-c0ff33-c0f3f3"
    x = RcHwInfo(
        fw_file="/dev/null",
        fw_signature="1234567890",
        product="Radiacode",
        model="RC-100",
        serial_number="RC-100-314159",
        hw_num=sentinel,
        boot_ver="4.0",
        fw_ver="4.12",
        boot_date=_BEGINNING_OF_TIME,
        fw_date=_THE_END_OF_DAYS,
    )
    d = x.as_dict()
    j = x.json()
    assert d["_dataclass"] is True
    assert d["_type"] == x.__class__.__name__
    assert "_dataclass" in j
    assert x.__class__.__name__ in j
    assert sentinel in j
    assert len(x.values()) == 10


def test_SGHeader():
    sentinel = "Look at the pretty green glass"
    x = SGHeader(
        timestamp=_BEGINNING_OF_TIME,
        duration=timedelta(seconds=3.14159),
        comment=sentinel,
    )
    d = x.as_dict()
    j = x.json()
    assert d["_dataclass"] is True
    assert d["_type"] == x.__class__.__name__
    assert "_dataclass" in j
    assert x.__class__.__name__ in j
    assert sentinel in j
    assert len(x.values()) == 7


def test_SpectrogramPoint_invalid_time():
    x = SpectrogramPoint(counts=[0], td=1)
    with pytest.raises(ValueError, match="uninitialized datetime somewhere"):
        x.json()


def test_SpectrogramPoint():
    x = SpectrogramPoint(dt=_BEGINNING_OF_TIME, td=3.14159, counts=[1, 2, 3, 4])
    d = x.as_dict()
    j = x.json()
    assert d["_dataclass"] is True
    assert d["_type"] == x.__class__.__name__
    assert "_dataclass" in j
    assert x.__class__.__name__ in j
    assert len(x.values()) == 3


def test_TrackPoint():
    sentinel = "Look at the pretty green glass"
    x = TrackPoint(
        dt=_BEGINNING_OF_TIME,
        latitude=0,
        longitude=1,
        accuracy=2,
        doserate=3,
        countrate=4,
        comment=sentinel,
    )
    d = x.as_dict()
    j = x.json()
    assert d["_dataclass"] is True
    assert d["_type"] == x.__class__.__name__
    assert "_dataclass" in j
    assert x.__class__.__name__ in j
    assert sentinel in j
    assert len(x.values()) == 7


def test_TimeRange():
    x = TimeRange(dt_end=_THE_END_OF_DAYS, dt_start=_BEGINNING_OF_TIME)
    d = x.as_dict()
    j = x.json()
    assert d["_dataclass"] is True
    assert d["_type"] == x.__class__.__name__
    assert "_dataclass" in j
    assert x.__class__.__name__ in j
    assert len(x.values()) == 2


def test_Spectrum():
    # 768 channels, just because that's not a typical value
    x = Spectrum(duration=314159, a2=1.5e-6, a1=2.5, a0=-2.3456, counts=[0] * 768)
    d = x.as_dict()
    j = x.json()
    assert d["_dataclass"] is True
    assert d["_type"] == x.__class__.__name__
    assert "_dataclass" in j
    assert x.__class__.__name__ in j
    v = x.values()
    assert len(v) == 5
    assert len(v[3]) == 768


def test_SpectrumLayer():
    sentinel = "Look at the pretty green glass"
    x = SpectrumLayer(
        spectrum_name="whatever",
        device_model="RC-100",
        serial_number="RC-100-123456",
        calibration=EnergyCalibration(a0=0, a1=1, a2=2),
        timestamp=_BEGINNING_OF_TIME,
        duration=123456,
        counts=[1] * 768,
        channels=768,
        comment=sentinel,
    )
    d = x.as_dict()
    j = x.json()
    assert d["_dataclass"] is True
    assert d["_type"] == x.__class__.__name__
    assert "_dataclass" in j
    assert x.__class__.__name__ in j
    assert sentinel in j
    assert len(x.values()) == 9


def test_SpecData():
    x = SpecData(
        monotime=1.7e9,
        time=_BEGINNING_OF_TIME,
        serial_number="RC-100-123456",
        spectrum=Spectrum(duration=10, a0=1, a1=2, a2=3, counts=[1] * 1024),
    )
    d = x.as_dict()
    j = x.json()
    assert d["_dataclass"] is True
    assert d["_type"] == x.__class__.__name__
    assert "_dataclass" in j
    assert x.__class__.__name__ in j
    assert len(x.values()) == 4


def test_SpecEnergy():
    x = SpecEnergy(dose=1, duration=timedelta(minutes=1), peak_dose=10)
    d = x.as_dict()
    j = x.json()
    assert d["_dataclass"] is True
    assert d["_type"] == x.__class__.__name__
    assert "_dataclass" in j
    assert x.__class__.__name__ in j
    assert len(x.values()) == 3


def test_RtData():
    x = RtData(monotime=1.7e9, dt=_THE_END_OF_DAYS, temperature=-273.15, charge_level=100)
    d = x.as_dict()
    j = x.json()
    assert d["_dataclass"] is True
    assert d["_type"] == x.__class__.__name__
    assert "_dataclass" in j
    assert x.__class__.__name__ in j
    assert len(x.values()) == 11


def test_GpsData():
    x = GpsData(
        monotime=1.7e9,
        payload=dict(gnss=True, time=_THE_END_OF_DAYS, lat=1, lon=2, mode=3, speed=4, climb=5, track=6, alt=7, epc=0),
    )
    d = x.as_dict()
    j = x.json()
    assert d["_dataclass"] is True
    assert d["_type"] == x.__class__.__name__
    assert "_dataclass" in j
    assert x.__class__.__name__ in j
    assert len(x.values()) == 2
