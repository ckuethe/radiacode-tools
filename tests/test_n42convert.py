#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import sys
import unittest
from io import StringIO
from os.path import dirname
from os.path import join as pathjoin
from unittest.mock import patch

import n42convert

testdir = pathjoin(dirname(__file__), "data")


class TestN42Convert(unittest.TestCase):
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

    i = "inputfile"
    b = "bgfile"
    o = "outputfile"
    u = "a86fbd68-14b5-4a14-a325-50472cf1bb2c"
    z = "thisIsNotAValidUuid"

    def test_load_spectrum_filename(self):
        n42convert.process_single_file(
            fg_file=pathjoin(testdir, "data_am241.xml"),
            bg_file=pathjoin(testdir, "data_am241.xml"),
            out_file="/dev/null",
            overwrite=True,
        )

    def test_argparse_no_uuid(self):
        with patch("sys.argv", [__file__, "-i", self.i, "-b", self.b, "-o", self.o]):
            parsed_args = n42convert.get_args()
            self.assertEqual(parsed_args.input, self.i)
            self.assertEqual(parsed_args.background, self.b)
            self.assertEqual(parsed_args.output, self.o)
            self.assertEqual(parsed_args.uuid, None)

    def test_argparse_has_uuid(self):
        with patch("sys.argv", [__file__, "-i", self.i, "-b", self.b, "-o", self.o, "-u", self.u]):
            parsed_args = n42convert.get_args()
            self.assertEqual(str(parsed_args.uuid), self.u)

    def test_argparse_empty_uuid(self):
        with patch("sys.argv", [__file__, "-i", self.i, "-b", self.b, "-o", self.o, "-u", ""]):
            parsed_args = n42convert.get_args()
            self.assertIsNone(parsed_args.uuid)

    def test_argparse_invalid_uuid(self):
        with patch("sys.argv", [__file__, "-i", self.i, "-b", self.b, "-o", self.o, "-u", self.z]):
            with self.assertRaises(SystemExit):
                n42convert.get_args()
