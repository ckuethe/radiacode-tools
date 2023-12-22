#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import sys
import n42convert
import unittest
from unittest.mock import patch
from io import StringIO
from os.path import dirname, join as pathjoin


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

    def test_load_spectrum_file_no_inputs(self):
        with self.assertRaises(ValueError) as cm:
            n42convert.load_radiacode_spectrum()
        self.assertEqual("One of filename or fileobj are required", cm.exception.args[0])

    def test_load_spectrum_file_two_inputs(self):
        with self.assertRaises(ValueError) as cm:
            n42convert.load_radiacode_spectrum("/dev/null", sys.stdin)
        self.assertEqual("Only one of filename or fileobj may be given", cm.exception.args[0])

    def test_load_spectrum_filename(self):
        data = n42convert.load_radiacode_spectrum(filename=pathjoin(testdir, "data_am241.xml"))

        fmt_cal = n42convert.format_calibration(data)
        fmt_spec = n42convert.format_spectrum(data)
        fmt_instr = n42convert.make_instrument_info(data)
        self.assertRegex(fmt_cal, r"<CoefficientValues>([-]?[0-9]+[.][0-9]+ ){3}</CoefficientValues>")
        self.assertIn('ChannelData compressionCode="None"', fmt_spec)
        self.assertIn("Spectroscopic Personal Radiation Detector", fmt_instr)
        self.assertRegex(fmt_instr, r"<RadInstrumentIdentifier>RC-[0-9-]+</RadInstrumentIdentifier>")

        spec = data["foreground"].pop("spectrum")
        self.assertDictEqual(data, self.am241_expected)

    def test_load_spectrum_no_serial_number(self):
        data = n42convert.load_radiacode_spectrum(filename=pathjoin(testdir, "data_am241.xml"))

        data["foreground"].pop("device_serial_number", None)
        fmt_instr = n42convert.make_instrument_info(data)
        self.assertNotIn("<RadInstrumentIdentifier>", fmt_instr)

    def test_load_spectrum_fail_bad_spectrum_length(self):
        with self.assertRaises(ValueError) as cm:
            n42convert.load_radiacode_spectrum(filename=pathjoin(testdir, "data_invalid_spectrum.xml"))
        self.assertIn("spectrum length", cm.exception.args[0])

    def test_load_spectrum_fail_bad_calibration_polynomial(self):
        with self.assertRaises(ValueError) as cm:
            n42convert.load_radiacode_spectrum(filename=pathjoin(testdir, "data_invalid_cal_inconsistent_order.xml"))
        self.assertIn("calibration polynomial", cm.exception.args[0])

    def test_load_spectrum_fail_bad_calibration_order(self):
        with self.assertRaises(ValueError) as cm:
            n42convert.load_radiacode_spectrum(filename=pathjoin(testdir, "data_invalid_cal_incorrect_order.xml"))
        self.assertIn("calibration order", cm.exception.args[0])

    def test_load_spectrum_fileobj(self):
        with open(pathjoin(testdir, "data_am241.xml")) as ifd:
            data = n42convert.load_radiacode_spectrum(fileobj=ifd)
            data["foreground"].pop("spectrum")
            self.assertDictEqual(data, self.am241_expected)

    def test_convert_fileobj(self):
        with open(pathjoin(testdir, "data_am241.xml")) as ifd:
            data = n42convert.process_single_fileobj(fileobj=ifd)
            self.assertIn("radiacode-csi-sipm", data)

    def test_load_spectrum_fileobj_big(self):
        fn = pathjoin(testdir, "data_th232_plus_background.xml")
        with patch("sys.stdout", new_callable=StringIO):
            n42convert.process_single_file(fn, out_file="/dev/stdout", overwrite=True)
        converted = sys.stdout.read()
        self.assertIn("Title: Th-232-BG", converted)
        self.assertIn("Title: BG 35hr", converted)
        self.assertIn("radiacode-csi-sipm", converted)

    def test_structure_fail(self):
        with self.assertRaises(Exception):
            n42convert.load_radiacode_spectrum("/dev/null")

    def test_squareformat_single(self):
        self.assertEqual(n42convert.squareformat([1], 1), "    1")

    def test_squareformat_multi(self):
        self.assertEqual(
            n42convert.squareformat(range(9), 3), "    0     1     2\n    3     4     5\n    6     7     8"
        ),

    def test_squareformat_notsquare(self):
        self.assertEqual(n42convert.squareformat(range(5), 3), "    0     1     2\n    3     4\n"),

    def test_squareformat_fail0(self):
        with self.assertRaises(ValueError):
            n42convert.squareformat([0], 0)

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
