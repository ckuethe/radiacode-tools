#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# Author: Chris Kuethe <chris.kuethe@gmail.com> , https://github.com/ckuethe/radiacode-tools
# SPDX-License-Identifier: MIT

"""
Some stuff found to be useful in various scripts, and should thus be hoisted into a
utility library, rather than being imported from and between scripts.
"""

from datetime import datetime, timedelta, timezone
from re import search as re_search
from typing import Any, Dict, List

from radiacode import RadiaCode

from rctypes import Number, SpecData

# The spectrogram format uses FileTime, the number of 100ns intervals since the
# beginning of 1600 CE. On a linux/unix/bsd host, we get the number of (fractional)
# seconds since the beginning of 1970 CE.

_filetime_quantum = 1e-7
_filetime_epoch_offset = 116444736000000000

UTC = timezone(timedelta(0))


def FileTime2UnixTime(x: Number) -> float:
    "Convert a FileTime to Unix timestamp"
    return (float(x) - _filetime_epoch_offset) * _filetime_quantum


def FileTime2DateTime(x: Number) -> datetime:
    "Convert a FileTime to Python DateTime"
    return datetime.fromtimestamp(FileTime2UnixTime(x), UTC)


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


def find_radiacode_devices() -> List[str]:
    "List all the radiacode devices detected"
    # defer import until someone calls this function
    from usb.core import find as usb_find

    return [  # No error handling. Caller can deal with any errors.
        d.serial_number
        for d in usb_find(idVendor=0x0483, idProduct=0xF123, find_all=True)
        if d.serial_number.startswith("RC-")
    ]


def get_device_id(dev: RadiaCode) -> Dict[str, str]:
    "Poll the device for all its identifiers"
    rv = {
        "fw": dev.fw_signature(),
        "fv": dev.fw_version(),
        "hw_num": dev.hw_serial_number(),
        "sernum": dev.serial_number(),
    }
    f = re_search(
        r'Signature: (?P<fw_signature>[0-9A-F]{8}), FileName="(?P<fw_file>.+?)", IdString="(?P<product>.+?)"',
        rv["fw"],
    )
    if f is None:
        raise ValueError("Couldn't parse device signature")

    rv.update(f.groupdict())
    rv.pop("fw")

    bv, fv = rv.pop("fv")
    rv["boot_ver"] = f"{bv[0]}.{bv[1]}"
    rv["boot_date"] = bv[2]
    rv["fw_ver"] = f"{fv[0]}.{fv[1]}"
    rv["fw_date"] = fv[2].strip("\x00")
    return rv


def probe_radiacode_devices() -> None:
    "'probe' might not be the right name; this finds connected devices and prints their device identifiers"
    for dev_id in find_radiacode_devices():
        rc = RadiaCode(serial_number=dev_id)
        d = get_device_id(dev=rc)
        print(
            "Found {product}\n"
            "Serial Number: {sernum}\n"
            "Boot {boot_ver} ({boot_date})\n"
            "Firmware {fw_ver} {fw_signature} ({fw_date}) \n"
            "HW ID {hw_num}".format_map(d),
            end="\n\n",
        )


def specdata_to_dict(data: SpecData) -> Dict[str, Any]:
    "Turn a SpecData into an easily jsonified dict"
    rec = {
        "timestamp": data.time,
        "serial_number": data.serial_number,
        "duration": data.spectrum.duration.total_seconds(),
        "calibration": [data.spectrum.a0, data.spectrum.a1, data.spectrum.a2],
        "counts": data.spectrum.counts,
    }
    return rec
