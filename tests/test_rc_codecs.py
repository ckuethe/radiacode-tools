#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import pytest

from radiacode_tools import rc_codecs

# Taken from the RFC
b45_pairs = [
    (b"AB", "BB8"),
    (b"Hello!!", "%69 VD92EX0"),
    (b"ietf!", "QED8WEX0"),
]

rle0_pairs = [
    ([1], [1]),
    ([0], [0, 1]),
    ([1, 0], [1, 0, 1]),
    ([1, 0, 2], [1, 0, 1, 2]),
    ([1, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 3], [1, 0, 3, 2, 0, 8, 3]),
    ([0] * 128, [0, 128]),
]

vbyte_pairs = [
    # smallest message: a single 8-bit zero
    ([0], b"\x01\x00\x00\x00"),
    # multiple 8-bit numbers, but not a multiple of 4
    ([1, 2], b"\x02\x00\x00\x01\x02"),
    # a multiple of 4 numbers
    ([1, 2, 3, 4], b"\x04\x00\x00\x01\x02\x03\x04"),
    # Test the full range of encoding, and not a multiple of 4 numbers
    (
        [
            0,
            1,
            0xFF,
            0x100,
            0xFFFF,
            0x10000,
            0xFFFFFF,
            0x1000000,
            0xFFFFFFFF,
        ],
        b"\x09\x00\x40\xe9\x03\x00\x01\xff\x00\x01\xff\xff\x00\x00\x01\xff\xff\xff\x00\x00\x00\x01\xff\xff\xff\xff",
    ),
]


def test_b45_encode():
    for x in b45_pairs:
        assert rc_codecs.b45_encode(x[0]) == x[1]


def test_b45_encode_strings():
    for x in b45_pairs:
        assert rc_codecs.b45_encode(x[0].decode()) == x[1]


def test_b45_decode_fail_bad_char():
    with pytest.raises(ValueError, match="substring not found") as cm:
        _ = rc_codecs.b45_decode("BB^")


def test_b45_decode():
    for x in b45_pairs:
        assert rc_codecs.b45_decode(x[1]) == x[0]


def test_b45_roundtrip():
    with open(__file__, "rb") as ifd:
        buf = ifd.read()
        assert rc_codecs.b45_decode(rc_codecs.b45_encode(buf)) == buf


def test_rle0_encode():
    for x in rle0_pairs:
        assert rc_codecs.rle0_encode(x[0]) == x[1]


def test_rle0_decode():
    for x in rle0_pairs:
        assert rc_codecs.rle0_decode(x[1]) == x[0]


def test_vbyte_encode():
    for x in vbyte_pairs:
        assert rc_codecs.vbyte_encode(x[0]) == x[1]


def test_vbyte_encode_fail():
    with pytest.raises(ValueError):
        rc_codecs.vbyte_encode([2**33])


def test_vbyte_decode():
    for x in vbyte_pairs:
        assert rc_codecs.vbyte_decode(x[1]) == x[0]


def test_vbyte_decode_padded():
    # trailing data is tolerated
    assert rc_codecs.vbyte_decode(b"\x02\x00\x00\x01\x02\x00") == [1, 2]
