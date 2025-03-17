#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# Author: Chris Kuethe <chris.kuethe@gmail.com> , https://github.com/ckuethe/radiacode-tools
# SPDX-License-Identifier: MIT

import base64
import datetime
import re
import zlib
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote_plus

from dateutil.parser import parse as dateparse

from .rc_codecs import (
    b45_decode,
    b45_encode,
    rle0_decode,
    rle0_encode,
    vbyte_decode,
    vbyte_encode,
)
from .rc_utils import Number

OPT_NO_DEFLATE = 0x01
OPT_NO_BASE_X = 0x02
OPT_USE_BASE64 = 0x10
OPT_CSV_SPECTRUM = 0x04
OPT_NO_SPEC_RLE0 = 0x08


def extract_metadata(uri: str, debug=False) -> Dict[str, Any]:
    "Given a RADDATA URL, produce a dict of metadata and the payload"
    rv = re.match(
        r"^(RADDATA|INTERSPEC)://G(?P<specver>\d)/(?P<options>[0-9a-f]{1,2})(?P<n_uris>[0-9a-f])(?P<n_spectra>[0-9a-f])/(?P<data>.+)",
        uri,
        re.I | re.S | re.M,
    ).groupdict()
    for f in ["specver", "n_uris", "n_spectra", "options"]:
        rv[f] = int(rv[f], 16)

    if rv["specver"] not in [0]:
        raise ValueError("Unsupported Version")

    valid_opts = 0x1F
    if rv["options"] & 0xFF > valid_opts:
        raise ValueError("Undefined option bits set")

    rv["deflated"] = False if rv["options"] & OPT_NO_DEFLATE else True
    rv["base_x_encoded"] = False if rv["options"] & OPT_NO_BASE_X else True
    rv["use_base64"] = True if rv["options"] & OPT_USE_BASE64 else False
    rv["csv_channel_data"] = True if rv["options"] & OPT_CSV_SPECTRUM else False
    rv["rle_zero_compress"] = False if rv["options"] & OPT_NO_SPEC_RLE0 else True

    if debug:
        headers = rv.copy()
        headers.pop("data")
        print(f"metadata debug: {headers}")

    return rv


def parse_payload_fields(msg: bytes, debug=False) -> Dict[str, Any]:
    """
    The payload can have a variable number of fields - k:v pairs - only two of which are
    required: live/real times (T) and the actual spectrum (S) data. The spectrum must be
    the last field in the message.

    This function does no quality checks, it just tries to
    """
    fields_data, spec_data = re.search(b"^([A-Z]:.*?)(?: S:)(.*)$", msg, re.M | re.I | re.S | re.DOTALL).groups()
    rv = dict()

    if debug:
        print(f"raw fields: {fields_data}")

    ml = re.split("( ?[A-Z]: ?)", " " + fields_data.decode(), re.M | re.S)[1:]

    if debug:
        print(f"split fields: {ml}")

    for i in range(0, len(ml), 2):
        k, v = (ml[i].strip()[0], ml[i + 1].strip())
        if debug:
            print(f"> '{k}'->'{v}'")
        if False:
            pass  # just so I can make a pretty list of elifs
        elif "I" == k:
            rv["type"] = v
        elif "T" == k:
            rv["meas_time"] = [float(f) for f in v.split(",")]
        elif "C" == k:
            rv["energy_calibration"] = [float(f) for f in v.split(",")]
        elif "M" == k:
            rv["model"] = v.strip()
        elif "P" == k:
            rv["timestamp"] = dateparse(v)
        elif "G" == k:
            rv["location"] = [float(f) for f in v.split(",")]
        elif "D" == k:
            rv["deviations"] = [float(f) for f in v.split(",")]
        elif "N" == k:
            rv["neutrons"] = int(v)
        elif "O" == k:
            rv["comment"] = v.strip()
        else:
            raise ValueError(f"Unknown field: {k}")

    rv["spec_data"] = spec_data
    return rv


def decode_qr_data(msg: str, debug: bool = False) -> Dict[str, Any]:
    "Main decoder. Given the text embodied in a QR Code, produce a dict of the measurement"
    rv = extract_metadata(msg, debug)

    # Payload may be some combination of URL encoded, base64 encoded, base45 encoded, and deflated
    payload = unquote_plus(rv["data"])
    if rv["base_x_encoded"]:
        if rv["use_base64"]:
            if debug:
                print("doing base64decode")
            payload = base64.b64decode(payload)
        else:
            if debug:
                print("doing base45decode")
            payload = b45_decode(payload)
    if rv["deflated"]:
        if debug:
            print("doing zlib decompress")
        payload = zlib.decompress(payload)

    # Payload now contains the k:v field pairs. Parse them.
    rv.update(parse_payload_fields(payload, debug))

    rv["channels"] = None
    if rv["csv_channel_data"]:
        counts = [int(x) for x in rv["spec_data"].split(b",")]
    else:
        counts = vbyte_decode(rv["spec_data"])

    if rv["rle_zero_compress"]:
        rv["counts"] = rle0_decode(counts)
    else:
        rv["counts"] = counts

    rv["channels"] = len(rv["counts"])
    # Don't need these any more
    rv.pop("spec_data")
    rv.pop("data")

    return rv


def make_qr_payload(
    *,
    lr_times: Tuple[Number, Number],
    spectrum: List[int],
    calibration: List[int] = None,
    deviations: Optional[List[Tuple[Number, Number]]] = None,
    mclass: Optional[str] = "",
    location: Optional[Tuple[Number, Number]] = None,
    detector_model: Optional[str] = "",
    neutron_count: Optional[int] = None,
    comments: Optional[str] = "",
    timestamp: Optional[datetime.datetime] = None,
    options: Optional[int] = 0,
):
    """
    Format the payload of the raddata/interspec qrcode

    lr_times [T]: required. live time and real ("wall") time. Live time <= real time. Tuple[Number,Number]
    spectrum [S]: required. counts in each detector channel. List[int]
    calibration [C]: calibration coefficients. List[Number]
    deviations [D]: energy deviation values. List[Tuple[Number,Number]]
    mclass [I]: item type, or MeasurementClass in N42 parlance. One of [FBICN]
    location [L]: location where the measurement was taken. Tuple[Number,Number]
    detector_model [M]: Freeform text describing the detector. str
    neutron_count [N]: Number of neutrons detected, presence implies neutron detection capability. int
    comment [O]: Freeform text. str
    timestamp [P]: when this measurement was taken. [datetime.datetime]

    (Playing fast and loose with the type annotations: Number is a float or int, List and Tuple are more or less equivalent)
    """
    fields = []

    text_flags = OPT_CSV_SPECTRUM | OPT_NO_DEFLATE | OPT_NO_BASE_X
    b45_text = text_flags == options & text_flags

    if mclass:
        if mclass in "FBICN":
            fields.append(f"I:{mclass}".encode())
        else:
            raise ValueError(f"Invalid measurement class ''{mclass}'")

    if timestamp and isinstance(timestamp, datetime.datetime):
        fields.append(f"P:{timestamp.strftime('%Y%m%dT%H%M%S')}".encode())

    detector_model = detector_model.strip()
    if detector_model:
        if b45_text:
            fields.append(f"M:{b45_encode(detector_model)}".encode())
        else:
            fields.append(f"M:{detector_model}".encode())

    comments = comments.strip()
    if comments:
        if b45_text:
            fields.append(f"O:{b45_encode(comments)}".encode())
        else:
            fields.append(f"O:{comments}".encode())

    if neutron_count is not None:
        if int(neutron_count) >= 0:
            fields.append(f"N:{int(neutron_count)}".encode())
        else:
            raise ValueError("neutron count cannot be negative")

    if deviations:
        if isinstance(deviations, list) or isinstance(deviations, tuple):
            dx = []
            for i in deviations:
                if len(i) != 2:
                    raise ValueError("Deviation entry must be length 2")
                dx.append(f"{i[0]},{i[1]}")
            dx = ",".join(dx)
            fields.append(f"D:{dx}".encode())
        else:
            raise ValueError("Deviations must be a list of 2-tuples of floats (energy,deviation)")

    if location:
        if isinstance(location, tuple) and len(location) == 2:  # in the future, altitude may also be supported
            lx = ",".join([str(f) for f in location])
            fields.append(f"G:{lx}".encode())
        else:
            raise ValueError("Location must be a list of 2 floats, for latitude and longitude")

    if calibration:
        if isinstance(calibration, list) or isinstance(calibration, tuple):
            cx = ",".join([str(round(f, 6)) for f in calibration])
            fields.append(f"C:{cx}".encode())

    if (isinstance(lr_times, tuple) or isinstance(lr_times, list)) and len(lr_times) == 2:
        _ = float(lr_times[0]) - float(lr_times[1])  # cause an exception unless these are both numeric
        if lr_times[0] > lr_times[1]:
            raise ValueError("live time cannot be greater than real time")
    else:
        raise ValueError("lr_times must be a 2-element list or tuple")
    fields.append(f"T:{lr_times[0]},{lr_times[1]}".encode())

    if not (options & OPT_NO_SPEC_RLE0):
        tmp = rle0_encode(spectrum)
        if len(tmp) >= len(spectrum):
            options |= OPT_NO_SPEC_RLE0
        else:
            spectrum = tmp

    if options & OPT_CSV_SPECTRUM:
        encoded_spectrum = ",".join([str(i) for i in spectrum]).encode()
    else:
        encoded_spectrum = vbyte_encode(spectrum)

    # deepcode ignore BadMixOfStrAndBytes: snyk doesn't realize that encoded_spectrum is always bytes
    fields.append(b"S:" + encoded_spectrum)

    fieldsep = b" "

    return options, fieldsep.join(fields)
