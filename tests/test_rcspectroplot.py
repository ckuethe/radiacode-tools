#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import unittest
from os.path import dirname
from os.path import join as pathjoin
from unittest.mock import patch

testdir = pathjoin(dirname(__file__), "data")
testfile = pathjoin(testdir, "K40.rcspg")
testndjson = pathjoin(testdir, "xray.ndjson")

from radiacode_tools.rc_files import RcSpectrogram
from rcspectroplot import filter_spectrogram, get_args, load_spectrogram_from_ndjson


class TestSpectroPlot(unittest.TestCase):
    def test_argparse_no_args(self):
        with patch("sys.argv", [__file__]):
            with self.assertRaises(SystemExit):
                get_args()

    def test_argparse_load_rcspg(self):
        with patch("sys.argv", [__file__, testfile]):
            args = get_args()
            spg = RcSpectrogram(args.input_file)
            n = len(spg.samples)
            filter_spectrogram(args, spg)
            self.assertEqual(len(spg.samples), n)

    def test_argparse_load_ndjson(self):
        with patch("sys.argv", [__file__, "-o", "/dev/null", testndjson]):
            args = get_args()
            spg = load_spectrogram_from_ndjson(args)
            n = len(spg.samples)
            filter_spectrogram(args, spg)
            self.assertEqual(len(spg.samples), n)

    def test_argparse_load_ndjson_no_serial_match(self):
        with patch("sys.argv", [__file__, "-s", "RC-100-314159", testndjson]):
            args = get_args()
            with self.assertRaises(SystemExit):
                load_spectrogram_from_ndjson(args)

    def test_rcspg_sampfilter_first(self):
        with patch("sys.argv", [__file__, "--sample", "0~0", testfile]):
            args = get_args()
            spg = RcSpectrogram(args.input_file)
            s = spg.samples[0]
            filter_spectrogram(args, spg)
            self.assertEqual(len(spg.samples), 1)
            self.assertEqual(spg.samples[0], s)

    def test_rcspg_sampfilter_all(self):
        with patch("sys.argv", [__file__, "--sample", "~", testfile]):
            args = get_args()
            spg = RcSpectrogram(args.input_file)
            n = len(spg.samples)
            filter_spectrogram(args, spg)
            self.assertEqual(len(spg.samples), n)

    def test_rcspg_timefilter_all(self):
        with patch("sys.argv", [__file__, "--time", "~", testfile]):
            args = get_args()
            spg = RcSpectrogram(args.input_file)
            n = len(spg.samples)
            filter_spectrogram(args, spg)
            self.assertEqual(len(spg.samples), n)

    def test_rcspg_timefilter_first(self):
        with patch("sys.argv", [__file__, "--time", "~2023-12-01T08:18:00Z", testfile]):
            args = get_args()
            spg = RcSpectrogram(args.input_file)
            s = spg.samples[0]
            filter_spectrogram(args, spg)
            self.assertEqual(len(spg.samples), 1)
            self.assertEqual(spg.samples[0], s)

    def test_rcspg_duration_all(self):
        with patch("sys.argv", [__file__, "--duration", "~", testfile]):
            args = get_args()
            spg = RcSpectrogram(args.input_file)
            n = len(spg.samples)
            filter_spectrogram(args, spg)
            self.assertEqual(len(spg.samples), n)

    def test_rcspg_duration_short(self):
        with patch("sys.argv", [__file__, "--duration", "~0:03:00", testfile]):
            args = get_args()
            spg = RcSpectrogram(args.input_file)
            filter_spectrogram(args, spg)
            self.assertEqual(len(spg.samples), 3)
