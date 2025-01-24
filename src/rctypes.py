#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# Author: Chris Kuethe <chris.kuethe@gmail.com> , https://github.com/ckuethe/radiacode-tools
# SPDX-License-Identifier: MIT

"""
All the special namedtuples used elsewhere
"""

from collections import namedtuple
from typing import Union

Number = Union[int, float]

_nan = float("nan")
TimeRange = namedtuple("TimeRange", ["t_start", "t_end"], defaults=[None, None])
GeoPoint = namedtuple("GeoPoint", ["latitude", "longitude"], defaults=[_nan, _nan])
GeoBox = namedtuple("GeoBox", ["p1", "p2"], defaults=[GeoPoint(), GeoPoint()])
GeoCircle = namedtuple("GeoCircle", ["point", "radius"], defaults=[GeoPoint(), _nan])

# Dead Time statistics
DTstats = namedtuple("DTstats", ["lost_cps", "loss_fraction", "dt_us", "dt_cps"])

# Channel to Energy calibration polynomial
EnergyCalibration = namedtuple("EnergyCalibration", ["a0", "a1", "a2"], defaults=[0, 3000 / 1024, 0])

# Kind of a dummy type but at least it helps me know what I'm passing around
GpsData = namedtuple("GpsData", ["payload"])

# Real Time data that the device produces more or less gratuitously.
# Some subset of these fields are present in each of the data types,
# this is just a convenient way to represent whatever is going on.
_rtdata_fields = [
    "time",
    "dt",
    "serial_number",
    "type",
    "count_rate",
    "count",
    "dose_rate",
    "dose",
    "charge_level",
    "temperature",
    "duration",
]
RtData = namedtuple("RtData", _rtdata_fields, defaults=[None] * len(_rtdata_fields))  # type: ignore[misc]

# Just like radiacode.types.Spectrum, but without having to import radiacode.
Spectrum = namedtuple("Spectrum", ["duration", "a0", "a1", "a2", "counts"])

# Spectrum XML files can have both a foreground and a background spectrum, which I call
# layers. Normally you don't mix a background and foreground from different devices, but
# since the radiacode app supports that, I have to as well. Also, you may have slightly
# calibrations between the foreground and background, so those are part of the layer as
# well.
_sl_fields = [
    "spectrum_name",
    "device_model",
    "serial_number",
    "comment",
    "calibration",
    "timestamp",
    "duration",
    "channels",
    "counts",
]
SpectrumLayer = namedtuple("SpectrumLayer", _sl_fields, defaults=[None] * len(_sl_fields))  # type: ignore[misc]

# A single
SpecData = namedtuple("SpecData", ["time", "serial_number", "spectrum"])

SpecEnergy = namedtuple("SpecEnergy", ["dose", "duration", "peak_dose"])

_sgheader_fields = ["name", "time", "timestamp", "channels", "duration", "flags", "comment"]
SGHeader = namedtuple("SGHeader", _sgheader_fields, defaults=[None] * len(_sgheader_fields))  # type: ignore[misc]

# A single datapoint, at least in this implementaton, is a timestamp and a collection of counts per channel.
# No integration time, since that's kind of implicit from the inter-sample timing
# "time" is kinda vague here; it could be either a timestamp of the sample or the duration
SpectrogramPoint = namedtuple("SpectrogramPoint", ["datetime", "timedelta", "counts"], defaults=[None, None, []])

# As you might expect a trackpoint is a datapoint from a radiacode track
# storing datetime as the canonical timestamp. It'll be transcoded for output
_trackpoint_fields = ["datetime", "latitude", "longitude", "accuracy", "doserate", "countrate", "comment"]
TrackPoint = namedtuple("TrackPoint", _trackpoint_fields, defaults=[None] * len(_trackpoint_fields))  # type: ignore[misc]


class RangeFinder:
    "A helper class to determine the range of a list"

    def __init__(self, name: str = "RangeFinder"):
        self.name = name
        self.min_val = None
        self.max_val = None

    def update(self, x):
        self.min_val = x if self.min_val is None else min(x, self.min_val)
        self.max_val = x if self.max_val is None else max(x, self.max_val)

    def get(self):
        return (self.min_val, self.max_val)

    def __str__(self):
        return f"{self.name}(min={self.min_val}, max={self.max_val})"

    def __repr__(self):
        print(self.__str__())
