#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# Author: Chris Kuethe <chris.kuethe@gmail.com> , https://github.com/ckuethe/radiacode-tools
# SPDX-License-Identifier: MIT

"""
Some stuff found to be useful in various scripts, and should thus be hoisted into a
utility library, rather than being imported from and between scripts.
"""

from dataclasses import is_dataclass
from datetime import datetime, timedelta, timezone
from re import search as re_search
from typing import Any, List

from radiacode import RadiaCode

from .rc_types import DATEFMT, DATEFMT_TZ, EnergyCalibration, Number, RcHwInfo

# The spectrogram format uses FileTime, the number of 100ns intervals since the
# beginning of 1600 CE. On a linux/unix/bsd host, we get the number of (fractional)
# seconds since the beginning of 1970 CE.

_filetime_quantum = 1e-7
_filetime_epoch_offset = 116444736000000000

UTC = timezone(timedelta(0))
localtz = datetime.now(timezone.utc).astimezone().tzinfo

# guess what happened here
_BEGINNING_OF_TIME_STR: str = "1945-07-16T11:29:21Z"
_BEGINNING_OF_TIME: datetime = datetime.strptime(_BEGINNING_OF_TIME_STR, DATEFMT_TZ).replace(tzinfo=UTC)
# https://pumas.nasa.gov/examples/how-many-days-are-year says approximately 365.25 days per year
# If you're still using python3 in 200 years, that's some serious retrocomputing
_THE_END_OF_DAYS: datetime = _BEGINNING_OF_TIME + timedelta(days=250 * 365.25)


def parse_datetime(ds: str, fmt: str = DATEFMT) -> datetime:
    return datetime.strptime(ds, fmt).replace(tzinfo=UTC)


def format_datetime(dt: datetime, fmt: str = DATEFMT) -> str:
    return dt.strftime(fmt)


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
    return UnixTime2FileTime(dt.replace(tzinfo=UTC).timestamp())


def stringify(a: List[Any], c: str = " ") -> str:
    "Make a string out of a list of things, nicer than str(list(...))"
    return c.join([f"{x}" for x in a])


def get_dose_from_spectrum(
    counts: List[int],
    cal: EnergyCalibration,
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

    def _chan2kev(cal: EnergyCalibration, c: int):
        return cal.a0 + cal.a1 * c + cal.a2 * c**2

    total_keV = sum([_chan2kev(cal, ch) * n for ch, n in enumerate(counts)])
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


def get_device_id(dev: RadiaCode) -> RcHwInfo:
    "Poll the device for all its identifiers"

    sig_match = re_search(
        r'Signature: (?P<fw_signature>[0-9A-F]{8}), FileName="(?P<fw_file>.+?)", IdString="(?P<product>.+?)"',
        dev.fw_signature(),
    )
    if sig_match is None:
        raise ValueError("Couldn't parse device signature")

    tfmt = "%b %d %Y %H:%M:%S"

    sig_fields = sig_match.groupdict()
    bv, fv = dev.fw_version()
    product, model = sig_fields["product"].split(" ")
    return RcHwInfo(
        fw_file=sig_fields["fw_file"],
        fw_signature=sig_fields["fw_signature"],
        product=product,
        model=model,
        serial_number=dev.serial_number(),
        hw_num=dev.hw_serial_number(),
        boot_ver=f"{bv[0]}.{bv[1]}",
        boot_date=datetime.strptime(bv[2], tfmt),
        fw_ver=f"{fv[0]}.{fv[1]}",
        fw_date=datetime.strptime(fv[2], tfmt),
    )


def probe_radiacode_devices() -> None:
    "'probe' might not be the right name; this finds connected devices and prints their device identifiers"
    for dev_id in find_radiacode_devices():
        rc = RadiaCode(serial_number=dev_id)
        d = get_device_id(dev=rc)
        print(
            f"Found {d.product}\n"
            f"Serial Number: {d.serial_number}\n"
            f"Boot {d.boot_ver} ({d.boot_date})\n"
            f"Firmware {d.fw_ver} {d.fw_signature} ({d.fw_date}) \n"
            f"HW ID {d.hw_num}",
            end="\n\n",
        )
