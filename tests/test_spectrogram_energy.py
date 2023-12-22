#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import spectrogram_energy
import unittest
from unittest.mock import patch
from io import StringIO
from os.path import dirname, join as pathjoin

test_dir = pathjoin(dirname(__file__), "data")


class TestSpectrogramEnergy(unittest.TestCase):
    header_fields = [
        "Spectrogram: unittest",
        "Time: 2023-11-23 00:20:09",
        "Timestamp: 133451904099380000",
        "Accumulation time: 182",
        "Channels: 1024",
        "Device serial: RC-102-001272",
        "Flags: 1",
        "Comment: ",
    ]

    def test_argparse_fail(self):
        with patch("sys.argv", [__file__, "--foobar"]):
            with self.assertRaises(SystemExit):
                spectrogram_energy.get_args()

    def test_argparse(self):
        with patch("sys.argv", [__file__, "--recursive", test_dir]):
            parsed_args = spectrogram_energy.get_args()
            self.assertEqual(parsed_args.recursive, True)
            self.assertEqual(parsed_args.files, [test_dir])

    def test_filetime_to_unixtime(self):
        parsed = spectrogram_energy.parse_header("\t".join(self.header_fields))
        self.assertEqual(parsed.name, "unittest")
        self.assertEqual(parsed.channels, 1024)
        self.assertEqual("2023-11-22 21:20:09.938000", str(parsed.timestamp))

    def test_extract_calibration(self):
        # a real spectrum line is about 12kB but we only need the first 16 hex-pairs
        spec_line = "Spectrum: 00 00 00 00 FC 35 CC C0 66 6B 17 40 82 97 E6 39 30"
        ec = spectrogram_energy.extract_calibration_from_spectrum(spec_line)
        self.assertAlmostEqual(ec.a0, -6.3816, delta=0.001)
        self.assertAlmostEqual(ec.a1, 2.3659, delta=0.001)
        self.assertAlmostEqual(ec.a2, 4.4e-5, delta=0.001)

    def test_parse_header(self):
        parsed = spectrogram_energy.parse_header("\t".join(self.header_fields))
        self.assertEqual(parsed.name, "unittest")
        self.assertEqual(parsed.channels, 1024)

    def test_parse_header_fail(self):
        hf = self.header_fields.copy()
        with self.assertRaises(ValueError):
            hf[4] = "Channels: 63"
            spectrogram_energy.parse_header("\t".join(hf))
        with self.assertRaises(ValueError):
            hf[4] = "Channels: 1025"
            spectrogram_energy.parse_header("\t".join(hf))

    def test_load_spectrogram_fail(self):
        with self.assertRaises(FileNotFoundError):
            spectrogram_energy.load_spectrogram(pathjoin(test_dir, "unobtainium.rcspg"))

    def test_load_spectrogram(self):
        sp = spectrogram_energy.load_spectrogram(pathjoin(test_dir, "K40.rcspg"))
        self.assertEqual(sp.duration, 43510)
        self.assertAlmostEqual(sp.dose, 2.12, delta=0.01)
        self.assertAlmostEqual(sp.peak_dose, 6.55e-5, delta=1e-7)

    def test_main(self):
        with patch("sys.argv", [__file__, "-v", "-r", test_dir]):
            with patch("sys.stdout", new=StringIO()) as mock_stdout:
                with patch("sys.stderr", new=StringIO()) as mock_stderr:
                    spectrogram_energy.main()

        self.assertIn("K40.rcspg: 2.12uSv in 43510s", mock_stdout.getvalue())  # from the K40 spectrogram
        self.assertIn("not enough values to unpack", mock_stderr.getvalue())  # from all the other test stuff
