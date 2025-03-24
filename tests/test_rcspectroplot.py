#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

from os.path import dirname
from os.path import join as pathjoin
from unittest.mock import patch

import pytest

testdir = pathjoin(dirname(__file__), "data")
testfile = pathjoin(testdir, "K40.rcspg")
testndjson = pathjoin(testdir, "xray.ndjson")

from radiacode_tools.rc_files import RcSpectrogram
from rcspectroplot import filter_spectrogram, get_args, load_spectrogram_from_ndjson


def test_argparse_no_args():
    with patch("sys.argv", [__file__]):
        with pytest.raises(SystemExit):
            get_args()


def test_argparse_load_rcspg():
    with patch("sys.argv", [__file__, testfile]):
        args = get_args()
        spg = RcSpectrogram(args.input_file)
        n = len(spg.samples)
        filter_spectrogram(args, spg)
        assert len(spg.samples) == n


def test_argparse_load_ndjson():
    with patch("sys.argv", [__file__, "-o", "/dev/null", testndjson]):
        args = get_args()
        spg = load_spectrogram_from_ndjson(args)
        n = len(spg.samples)
        filter_spectrogram(args, spg)
        assert len(spg.samples) == n


def test_argparse_load_ndjson_no_serial_match():
    with patch("sys.argv", [__file__, "-s", "RC-100-314159", testndjson]):
        args = get_args()
        with pytest.raises(SystemExit):
            load_spectrogram_from_ndjson(args)


def test_rcspg_sampfilter_first():
    with patch("sys.argv", [__file__, "--sample", "0~0", testfile]):
        args = get_args()
        spg = RcSpectrogram(args.input_file)
        s = spg.samples[0]
        filter_spectrogram(args, spg)
        assert len(spg.samples) == 1
        assert spg.samples[0] == s


def test_rcspg_sampfilter_all():
    with patch("sys.argv", [__file__, "--sample", "~", testfile]):
        args = get_args()
        spg = RcSpectrogram(args.input_file)
        n = len(spg.samples)
        filter_spectrogram(args, spg)
        assert len(spg.samples) == n


def test_rcspg_timefilter_all():
    with patch("sys.argv", [__file__, "--time", "~", testfile]):
        args = get_args()
        spg = RcSpectrogram(args.input_file)
        n = len(spg.samples)
        filter_spectrogram(args, spg)
        assert len(spg.samples) == n


def test_rcspg_timefilter_first():
    with patch("sys.argv", [__file__, "--time", "~2023-12-01T08:18:00Z", testfile]):
        args = get_args()
        spg = RcSpectrogram(args.input_file)
        s = spg.samples[0]
        filter_spectrogram(args, spg)
        assert len(spg.samples) == 1
        assert spg.samples[0] == s


def test_rcspg_duration_all():
    with patch("sys.argv", [__file__, "--duration", "~", testfile]):
        args = get_args()
        spg = RcSpectrogram(args.input_file)
        n = len(spg.samples)
        filter_spectrogram(args, spg)
        assert len(spg.samples) == n


def test_rcspg_duration_short():
    with patch("sys.argv", [__file__, "--duration", "~0:03:00", testfile]):
        args = get_args()
        spg = RcSpectrogram(args.input_file)
        filter_spectrogram(args, spg)
        assert len(spg.samples) == 3
