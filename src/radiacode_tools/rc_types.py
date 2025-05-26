#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# Author: Chris Kuethe <chris.kuethe@gmail.com> , https://github.com/ckuethe/radiacode-tools
# SPDX-License-Identifier: MIT

"""
All the special data types used elsewhere
"""

from dataclasses import dataclass, field, is_dataclass
from datetime import MINYEAR, datetime, timedelta
from json import JSONEncoder
from typing import Any, Dict, Iterable, List, Tuple, Union

from radiacode.types import Enum as RadiacodeEnum
from radiacode.types import Spectrum as RadiacodeSpectrum

Number = Union[int, float]

# preferred color palette choices for plotting
palettes: List[str] = ["jet", "plasma", "magma", "rainbow", "thermal", "turbo", "viridis"]

# there's enough time conversion it's worth having common definitions of the formats
DATEFMT: str = "%Y-%m-%d %H:%M:%S"
DATEFMT_Z: str = DATEFMT + "%z"
DATEFMT_T: str = DATEFMT.replace(" ", "T")
DATEFMT_TZ: str = DATEFMT_T + "Z"

_nan = float("nan")  # didn't want to import math.nan
# this will throw a ValueError if you .timestamp() it and is therefore a good
# sentinel value. "outtatime" is, of course, a "Back to the Future" reference.
_outtatime = datetime(MINYEAR, 1, 1, 0, 0, 0)


class RcJSONEncoder(JSONEncoder):
    "Encoder that supports all these custom types"

    def default(self, o):
        if isinstance(o, datetime):
            if o == _outtatime:
                raise ValueError("You've got an uninitialized datetime somewhere...")
            # FFS json, you really don't know how to deal with a datetime?!
            return o.isoformat()
        elif isinstance(o, timedelta):
            return o.total_seconds()
        elif isinstance(o, RadiacodeEnum):
            return o.name
        elif hasattr(o, "as_dict"):
            return o.as_dict()
        elif is_dataclass(o):
            # My custom dataclasses use a mixin to add an as_dict implmentation, which will be called
            # above. If I come across a dataclass that doesn't provide this functionality, then this
            # encoder will perform similar operations. The presence of a `_dataclass` member tells me
            # that the json object was a originally dataclass and when decoded that a dataclass
            # should be generated rather than a dict.
            rv = dict(o.__dict__)  # make a copy because I'll be adding fields
            rv["_dataclass"] = True
            rv["_type"] = o.__class__.__name__
            return rv

        return super().default(o)


class DataclassEncoderMixin:
    """
    Helper to add as_dict() and values() to every dataclass

    - as_dict() includes a `_dataclass` member to indicate the source dataclass type.
      The keys are `sorted()` for the benefit of other callers, like values()
    - values() function returns just values of the non metadata fields
    - json() like a __repr__, but in json
    """

    def as_dict(self, hide_dataclass: bool = False) -> Dict[str, Any]:
        rv = {x: getattr(self, x) for x in sorted(self.__dataclass_fields__.keys())}  # type: ignore
        if hide_dataclass is False:
            rv["_dataclass"] = True
            rv["_type"] = self.__class__.__name__
        return rv

    def json(self, **kwargs):
        return RcJSONEncoder(**kwargs).encode(self)

    def values(self) -> Tuple:
        return tuple(self.as_dict(hide_dataclass=True).values())


@dataclass(kw_only=True)
class TimeRange(DataclassEncoderMixin):
    dt_start: datetime = _outtatime
    dt_end: datetime = _outtatime


@dataclass(kw_only=True)
class GeoPoint(DataclassEncoderMixin):
    latitude: float
    longitude: float


@dataclass(kw_only=True)
class GeoBox(DataclassEncoderMixin):
    p1: GeoPoint
    p2: GeoPoint


@dataclass(kw_only=True)
class GeoCircle(DataclassEncoderMixin):
    point: GeoPoint
    radius: float


# Dead Time statistics
@dataclass(kw_only=True)
class DTstats(DataclassEncoderMixin):
    lost_cps: float = _nan
    loss_fraction: float = _nan
    dt_us: float = _nan
    dt_cps: float = _nan


# Channel to Energy calibration polynomial
@dataclass(kw_only=True)
class EnergyCalibration(DataclassEncoderMixin):
    a0: float
    a1: float
    a2: float


# Used primarily by rcmulispg to geotag measurements
@dataclass(kw_only=True)
class GpsData(DataclassEncoderMixin):
    payload: Dict[str, Any] = field(default_factory=dict)
    monotime: float


# Real Time data that the device produces more or less gratuitously.
# Some subset of these fields are present in each of the data types,
# this is just a convenient way to represent whatever is going on.
@dataclass(kw_only=True)
class RtData(DataclassEncoderMixin):
    dt: datetime = _outtatime
    serial_number: str = ""
    type: str = ""
    count_rate: float = _nan
    count: int = 0
    dose_rate: float = _nan
    dose: float = _nan
    charge_level: int = 0
    temperature: float = _nan
    duration: timedelta = timedelta(0)
    monotime: float


@dataclass(kw_only=True)
class RcHwInfo(DataclassEncoderMixin):
    fw_file: str
    fw_signature: str
    product: str
    model: str
    serial_number: str
    hw_num: str
    boot_ver: str
    boot_date: datetime
    fw_ver: str
    fw_date: datetime


# Augment radiacode.types.Spectrum with my encoder mixin
@dataclass
class Spectrum(RadiacodeSpectrum, DataclassEncoderMixin):
    pass


# Spectrum XML files can have both a foreground and a background spectrum, which I call
# layers. Normally you don't mix a background and foreground from different devices, but
# since the radiacode app supports that, I have to as well. Also, you may have slightly
# calibrations between the foreground and background, so those are part of the layer as
# well.
@dataclass(kw_only=True)
class SpectrumLayer(DataclassEncoderMixin):
    spectrum_name: str = "Unnamed spectrum"
    device_model: str = ""
    serial_number: str = ""
    timestamp: datetime = _outtatime
    duration: timedelta = timedelta(0)
    comment: str = ""
    channels: int
    counts: List[int]
    calibration: EnergyCalibration


# A single
@dataclass(kw_only=True)
class SpecData(DataclassEncoderMixin):
    monotime: float = _nan
    dt: datetime = _outtatime
    serial_number: str
    spectrum: Spectrum


@dataclass(kw_only=True)
class SpecEnergy(DataclassEncoderMixin):
    dose: float
    duration: timedelta = timedelta(0)
    peak_dose: float


@dataclass(kw_only=True)
class SGHeader(DataclassEncoderMixin):
    timestamp: datetime = _outtatime
    time: str = ""
    duration: timedelta = timedelta(0)
    name: str = ""
    channels: int = 1024
    flags: int = 0
    comment: str = ""


# A single datapoint, at least in this implementaton, is a timestamp and a collection of counts per channel.
# No integration time, since that's kind of implicit from the inter-sample timing
# "time" is kinda vague here; it could be either a timestamp of the sample or the duration
@dataclass(kw_only=True)
class SpectrogramPoint(DataclassEncoderMixin):
    counts: List[int]
    td: timedelta
    dt: datetime = _outtatime


# As you might expect a trackpoint is a datapoint from a radiacode track
# storing datetime as the canonical timestamp. It'll be transcoded for output
@dataclass(kw_only=True)
class TrackPoint(DataclassEncoderMixin):
    latitude: float
    longitude: float
    accuracy: float
    doserate: float
    countrate: float
    comment: str = ""
    dt: datetime = _outtatime


class RangeFinder:
    "A helper class to determine the range of a list"

    def __init__(self, name: str = "RangeFinder") -> None:
        self.name = name
        self.min_val = None
        self.max_val = None

    def add(self, l: Iterable) -> None:
        _ = [self.update(x) for x in l]

    def update(self, x):
        self.min_val = x if self.min_val is None else min(x, self.min_val)
        self.max_val = x if self.max_val is None else max(x, self.max_val)

    def get(self) -> Tuple[Any, Any]:
        return (self.min_val, self.max_val)

    def __str__(self):
        return f"{self.name}(min={self.min_val}, max={self.max_val})"

    def __repr__(self):
        print(self.__str__())
        print(self.__str__())
        print(self.__str__())
