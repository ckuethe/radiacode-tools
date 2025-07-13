#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# Author: Chris Kuethe <chris.kuethe@gmail.com> , https://github.com/ckuethe/radiacode-tools
# SPDX-License-Identifier: MIT

import struct
from typing import Union

_B45C = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:"  # defined in RFC9285


def b45_encode(s: Union[str, bytearray]) -> str:
    "Encode a string or bytearray into a base45 ASCII *string*"
    rv: list[str] = []
    if isinstance(s, str):
        s = bytearray(s, "utf-8")
    padded = False
    intval: int = 0
    for i in range(0, len(s), 2):
        try:
            intval = s[i] * 256 + s[i + 1]
        except IndexError:
            intval = s[i]
            padded = True

        r, x = divmod(intval, 45)
        z, y = divmod(r, 45)

        rv.extend([_B45C[c] for c in (x, y, z)])

    if padded:
        rv.pop(-1)
    return "".join(rv)


def b45_decode(s: str) -> bytes:
    """
    Decode a base45 ASCII string into bytes; original content may have been bytes.
    This will raise if an input character is not found in the _B45C character set.
    """
    rv: list[int] = []
    padded = False
    for i in range(0, len(s), 3):
        v: list[int] = [_B45C.index(c) for c in s[i : i + 3]]
        if len(v) < 3:
            v.extend([0] * (3 - len(v)))
            padded = True
        n: int = v[0] + v[1] * 45 + v[2] * 45**2
        a, b = divmod(n, 256)
        if padded:
            rv.append(b)
        else:
            rv.extend((a, b))
    return bytes(rv)


def rle0_encode(L: list[int]) -> list[int]:
    "N42 CountedZeros. It's run length encoding, but only for zero value"
    rv: list[int] = []
    nz = 0
    for v in L:
        if v:
            if nz:
                rv.extend((0, nz))
                nz = 0
            rv.append(v)
        else:
            nz += 1
    if nz:
        rv.extend((0, nz))
    return rv


def rle0_decode(L: list[int]) -> list[int]:
    "Expand N42 CountedZeros into the uncompressed form"
    i = 0
    n: int = len(L)
    rv: list[int] = []
    while i < n:
        if L[i] == 0:
            rv.extend([0] * L[i + 1])
            i += 2
        else:
            rv.append(L[i])
            i += 1

    return rv


def vbyte_encode(numbers: list[int]) -> bytes:
    """
    Compress a list of uint32 using variable length encoding. Much smaller than encoding everything as
    four byte ints or strings (up to 9 characters each). To be clear: every value must fit into uint32.
    """
    if all([0 <= i <= 0xFFFFFFFF for i in numbers]) is False:
        raise ValueError("All values must fit into unsigned 32-bit integer")

    payload_len: int = len(numbers)
    npad: int = payload_len % 4
    if npad:
        numbers = numbers + [0] * (4 - npad)

    control_bytes: list[bytes] = []
    data_bytes: list[bytes] = []

    for i in range(0, len(numbers), 4):
        cb = 0
        for k in range(4):
            n: int = numbers[i + k]
            if n <= 0xFF:
                cb |= 0 << (2 * k)
                data_bytes.append(struct.pack("<B", n))
            elif n <= 0xFFFF:
                cb |= 1 << (2 * k)
                data_bytes.append(struct.pack("<H", n))
            elif n <= 0xFFFFFF:
                cb |= 2 << (2 * k)
                data_bytes.append(struct.pack("<I", n)[0:3])
            else:  # don't need to explicitly check that n <= 0xFFFFFFFF
                cb |= 3 << (2 * k)
                data_bytes.append(struct.pack("<I", n))

        control_bytes.append(struct.pack("<B", cb))
        # Documentation of vbyte is pretty bad about dealing with partial blocks. There isn't any
        # in-band length indication so [0 0] doesn't tell me if there is a single zero or the data
        # got truncated in transit. It would be nicer if one could rely on having a multiple of
        # four encoded ints in the data stream.
        if npad:
            data_bytes = data_bytes[:payload_len]
    return b"".join([struct.pack("<H", payload_len), b"".join(control_bytes), b"".join(data_bytes)])


def vbyte_decode(vbz: bytes) -> list[int]:
    "decompress vbyte encoded data into a regular list of ints"
    rv: list[int] = []
    hl = 2
    nn = 0

    payload_len: int = struct.unpack("<H", vbz[:hl])[0]
    nctl: int = (payload_len + 3) // 4

    ctl_bytes: bytes = vbz[hl : hl + nctl]
    data_bytes: bytes = vbz[hl + nctl :] + b"\0\0\0\0"

    for cb in ctl_bytes:
        nb: list[int] = [((cb >> (2 * k)) & 0x03) + 1 for k in range(4)]
        for bl in nb:
            if bl == 1:
                rv.append(data_bytes[nn])
            if bl == 2:
                rv.append(struct.unpack("<H", data_bytes[nn : nn + bl])[0])
            if bl == 3:
                rv.append(struct.unpack("<H", data_bytes[nn : nn + 2])[0] + (data_bytes[nn + 2] << 16))
            if bl == 4:
                rv.append(struct.unpack("<I", data_bytes[nn : nn + bl])[0])
            nn += bl

    return rv[:payload_len]
