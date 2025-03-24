#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

from os.path import dirname
from os.path import join as pathjoin
from unittest.mock import patch

import pytest

import n42convert

testdir = pathjoin(dirname(__file__), "data")


am241_expected = {
    "device_name": "RadiaCode-102",
    "start_time": "2023-06-07T05:52:00",
    "end_time": "2023-06-07T06:02:13",
    "foreground": {
        "name": "Am-241",
        "device_serial_number": "RC-102-000115",
        "calibration_order": 2,
        "calibration_values": [-6.2832313, 2.4383054, 0.0003818],
        "duration": 613,
        "channels": 1024,
    },
    "background": None,
}

INPUTFILE = "inputfile"
BGFILE = "bgfile"
OUTPUTFILE = "outputfile"
UUID = "a86fbd68-14b5-4a14-a325-50472cf1bb2c"
NOTUUID = "thisIsNotAValidUuid"


def test_load_spectrum_filename():
    n42convert.process_single_file(
        fg_file=pathjoin(testdir, "data_am241.xml"),
        bg_file=pathjoin(testdir, "data_am241.xml"),
        out_file="/dev/null",
        overwrite=True,
    )


def test_argparse_no_uuid():
    with patch("sys.argv", [__file__, "-i", INPUTFILE, "-b", BGFILE, "-o", OUTPUTFILE]):
        parsed_args = n42convert.get_args()
        assert parsed_args.input == INPUTFILE
        assert parsed_args.background == BGFILE
        assert parsed_args.output == OUTPUTFILE
        assert parsed_args.uuid is None


def test_argparse_has_uuid():
    with patch("sys.argv", [__file__, "-i", INPUTFILE, "-b", BGFILE, "-o", OUTPUTFILE, "-u", UUID]):
        parsed_args = n42convert.get_args()
        assert str(parsed_args.uuid) == UUID


def test_argparse_empty_uuid():
    with patch("sys.argv", [__file__, "-i", INPUTFILE, "-b", BGFILE, "-o", OUTPUTFILE, "-u", ""]):
        parsed_args = n42convert.get_args()
        assert parsed_args.uuid is None


def test_argparse_invalid_uuid():
    with patch("sys.argv", [__file__, "-i", INPUTFILE, "-b", BGFILE, "-o", OUTPUTFILE, "-u", NOTUUID]):
        with pytest.raises(SystemExit):
            n42convert.get_args()
