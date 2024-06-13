#!/usr/bin/env python3
"""
All the special namedtuples used elsewhere
"""

from collections import namedtuple
from typing import Union

Number = Union[int, float]

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
RtData = namedtuple("RtData", _rtdata_fields, defaults=[None] * len(_rtdata_fields))

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
SpectrumLayer = namedtuple("SpectrumLayer", _sl_fields, defaults=[None] * len(_sl_fields))

# A single
SpecData = namedtuple("SpecData", ["time", "serial_number", "spectrum"])

SpecEnergy = namedtuple("SpecEnergy", ["dose", "duration", "peak_dose"])

_sgheader_fields = ["name", "time", "timestamp", "channels", "duration", "flags", "comment"]
SGHeader = namedtuple("SGHeader", _sgheader_fields, defaults=[None] * len(_sgheader_fields))

# A single datapoint, at least in this implementaton, is a timestamp and a collection of counts per channel.
# No integration time, since that's kind of implicit from the inter-sample timing
# "time" is kinda vague here; it could be either a timestamp of the sample or the duration
SpectrogramPoint = namedtuple("SpectrogramPoint", ["timestamp", "timedelta", "counts"], defaults=[None, None, []])

# As you might expect a trackpoint is a datapoint from a radiacode track
# storing datetime as the canonical timestamp. It'll be transcoded for output
_trackpoint_fields = ["datetime", "latitude", "longitude", "accuracy", "doserate", "countrate", "comment"]
TrackPoint = namedtuple("TrackPoint", _trackpoint_fields, defaults=[None] * len(_trackpoint_fields))
