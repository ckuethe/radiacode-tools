#!/usr/bin/env python3

"""
Some stuff found to be useful in various scripts, and should thus be hoisted into a
utility library, rather than being imported from and between scripts.
"""

import os
from binascii import hexlify
from collections import namedtuple
from datetime import datetime
from re import search as re_search
from re import sub as re_sub
from struct import pack as struct_pack
from tempfile import mkstemp
from time import gmtime, strftime
from typing import Any, Dict, List, Union

from radiacode import RadiaCode, Spectrum

# custom types
Number = Union[int, float]
_rt_fields = [
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
RtData = namedtuple("RtData", _rt_fields, defaults=[None] * len(_rt_fields))
SpecData = namedtuple("SpecData", ["time", "serial_number", "spectrum"])

# The spectrogram format uses FileTime, the number of 100ns intervals since the
# beginning of 1600 CE. On a linux/unix/bsd host, we get the number of (fractional)
# seconds since the beginning of 1970 CE.

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


def find_radiacode_devices() -> List[str]:
    "List all the radiacode devices detected"
    import usb.core  # defer import until someone calls this function

    return [  # No error handling. Caller can deal with any errors.
        d.serial_number
        for d in usb.core.find(idVendor=0x0483, idProduct=0xF123, find_all=True)
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
    ).groupdict()
    rv.update(f)
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


def rcspg_make_header(
    duration: int,
    serial_number: str,
    start_time: Number,
    name: str = "",
    comment: str = "",
    flags: int = 1,
    channels: int = 1024,
) -> str:
    """
    Create the first (header) line of the spectrum file

    Not all flag values are known, but bit 0 being unset means that the
    spectrogram recording was interrupted and resumed.
    """

    start_time = float(start_time)  # accept reasonable inputs: 1700000000, 1.7e9, "1.7e9", ...
    file_time = UnixTime2FileTime(start_time)
    gt = gmtime(start_time)
    tstr = strftime("%Y-%m-%d %H:%M:%S", gt)  # This one is for the header

    if not name:
        # and this version of time just looks like an int... for deduplication
        name = f"rcmulti-{strftime('%Y%m%d%H%M%S', gt)}-{serial_number}"

    fields = [
        f"Spectrogram: {name.strip()}",
        f"Time: {tstr}",
        f"Timestamp: {file_time}",
        f"Accumulation time: {int(duration)}",
        f"Channels: {channels}",
        f"Device serial: {serial_number.strip()}",
        f"Flags: {flags}",
        f"Comment: {comment}",
    ]
    return "\t".join(fields)


def rcspg_make_spectrum_line(x: Spectrum) -> str:
    """
    The second line of the spectrogram is the spectrum of the accumulated exposure
    since last data reset.
    (duration:int, coeffs:float[3], counts:int[1024])
    """
    v = struct_pack("<Ifff1024I", int(x.duration.total_seconds()), x.a0, x.a1, x.a2, *x.counts)
    v = hexlify(v, sep=" ").decode()
    return f"Spectrum: {v}"


def rcspg_format_spectra(data: List[SpecData]) -> str:
    """
    Given the list of SpecData, convert them to whatever we need for the spectrogram

    data[0] = all-time accumulated spectrum - survives "reset accumulation"
    data[1] = current accumulated spectrum at the start of measurement. needed to compute
    data[2:] = the rest of the spectra
    """
    lines = []
    prev_rec = data[1]
    for rec in data[2:]:
        ts = rec.time
        line = [UnixTime2FileTime(ts), int(ts - prev_rec.time)]
        line.extend([int(x[0] - x[1]) for x in zip(rec.spectrum.counts, prev_rec.spectrum.counts)])
        prev_rec = rec
        line = "\t".join([str(x) for x in line])
        line = re_sub(r"(\s0)+$", "", line)
        lines.append(line)

    return "\n".join(lines)


def rcspg_save_spectrogram_file(
    data: List[SpecData],
    serial_number: str,
    prefix: str = "rcmulti_",
) -> None:
    """
    Emit a spectrogram file into the current directory.
    """
    duration = data[-1].time - data[2].time
    start_time = data[0].time
    time_string = strftime("%Y%m%d%H%M%S", gmtime(start_time))
    fn = f"{prefix}{serial_number}_{time_string}.rcspg"

    header = rcspg_make_header(
        duration=duration,
        serial_number=serial_number,
        start_time=start_time,
    )
    print(f"saving spectrogram in {fn}")

    tfd, tfn = mkstemp(dir=".")
    os.close(tfd)
    with open(tfn, "wt") as ofd:
        print(header, file=ofd)
        print(rcspg_make_spectrum_line(data[-1].spectrum), file=ofd)
        print(rcspg_format_spectra(data), file=ofd)
    os.rename(tfn, fn)


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
