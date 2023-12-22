#!/usr/bin/env python3

"""
Some stuff found to be useful in various scripts, and should thus be hoisted into a
utility library, rather than being imported from and between scripts.
"""

from datetime import datetime
from typing import Union, List, Any

Number = Union[int, float]

# The spectrogram format uses FileTime, the number of 100ns intervals since the
# beginning of 1600 CE. On a linux/unix/bsd host, we get the number of (fractional)
# seconds since the beginning of 1970 CE. Here are some conversions, which, If I use
# them one more time are getting moved into a utility file...

_filetime_quantum = 1e-7
_filetime_epoch_offset = 116444736000000000


def FileTime2UnixTime(x: Number) -> float:
    "Convert a FileTime to Unix timestamp"
    return (float(x) - _filetime_epoch_offset) * _filetime_quantum


def FileTime2DateTime(x: Number) -> datetime:
    "Convert a FileTime to Python DateTime"
    return datetime.fromtimestamp(FileTime2UnixTime(x))


def UnixTime2FileTime(x: Number) -> int:
    "Convert a Unix timestamp to FileTime"
    return int(float(x) / _filetime_quantum + _filetime_epoch_offset)


def DateTime2FileTime(dt: datetime) -> int:
    "Convert a Python DateTime to FileTime"
    return UnixTime2FileTime(dt.timestamp())


def stringify(a: List[Any], c: str = " ") -> str:
    "Make a string out of a list of things, nicer than str(list(...))"
    return c.join([f"{x}" for x in a])


def get_dose_from_spectrum(
    counts: List[int],
    a0: float = 0,
    a1: float = 3000 / 1024,
    a2: float = 0,
    d: float = 4.51,
    v: float = 1.0,
) -> float:
    """
    A somewhat generic function to estimate the energy represented by a spectrum.

    counts: a list of counts per channel
    a0-a2 are the calibration coefficients for the instrument
    d: density in g/cm^3 of the scintillator crystal, approximately 4.51 for CsI:Tl
    v: volume of the scintillator crystal, radiacode is 1cm^3
    """

    joules_per_keV = 1.60218e-16
    mass = d * v * 1e-3  # kg

    def _chan2kev(c):
        return a0 + a1 * c + a2 * c**2

    total_keV = sum([_chan2kev(ch) * n for ch, n in enumerate(counts)])
    gray = total_keV * joules_per_keV / mass
    uSv = gray * 1e6
    return uSv
