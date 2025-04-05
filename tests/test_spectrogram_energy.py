#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import sys
from io import StringIO
from os.path import dirname
from os.path import join as pathjoin

import pytest

import spectrogram_energy

test_dir = pathjoin(dirname(__file__), "data")


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


def test_argparse_fail(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, "--foobar"])
    with pytest.raises(SystemExit):
        spectrogram_energy.get_args()


def test_argparse(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, "--recursive", test_dir])
    parsed_args = spectrogram_energy.get_args()
    assert parsed_args.recursive is True
    assert parsed_args.files == [test_dir]


def test_filetime_to_unixtime():
    parsed = spectrogram_energy.parse_header("\t".join(header_fields))
    assert parsed.name == "unittest"
    assert parsed.channels == 1024
    assert "2023-11-23 05:20:09.938000+00:00" == str(parsed.timestamp)


def test_extract_calibration():
    # a real spectrum line is about 12kB but we only need the first 16 hex-pairs
    spec_line = "Spectrum: 00 00 00 00 FC 35 CC C0 66 6B 17 40 82 97 E6 39 30"
    ec = spectrogram_energy.extract_calibration_from_spectrum(spec_line)
    assert pytest.approx(ec.a0, abs=1e-3) == -6.3816
    assert pytest.approx(ec.a1, abs=1e-3) == 2.3659
    assert pytest.approx(ec.a2, abs=1e-3) == 4.4e-5


def test_parse_header():
    parsed = spectrogram_energy.parse_header("\t".join(header_fields))
    assert parsed.name == "unittest"
    assert parsed.channels == 1024


def test_parse_header_fail():
    hf = header_fields.copy()
    with pytest.raises(ValueError):
        hf[4] = "Channels: 63"
        spectrogram_energy.parse_header("\t".join(hf))
    with pytest.raises(ValueError):
        hf[4] = "Channels: 1025"
        spectrogram_energy.parse_header("\t".join(hf))


def test_load_spectrogram_fail():
    with pytest.raises(FileNotFoundError):
        spectrogram_energy.load_spectrogram(pathjoin(test_dir, "unobtainium.rcspg"))


@pytest.mark.slow
def test_load_spectrogram():
    sp = spectrogram_energy.load_spectrogram(pathjoin(test_dir, "K40.rcspg"))
    assert sp.duration.total_seconds() == 43510
    assert pytest.approx(sp.dose, abs=0.01) == 2.12
    assert pytest.approx(sp.peak_dose, abs=1e-3) == 6.55e-5


@pytest.mark.slow
def test_main(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, "-v", "-r", test_dir])
    monkeypatch.setattr(sys, "stdout", StringIO())
    monkeypatch.setattr(sys, "stderr", StringIO())
    spectrogram_energy.main()

    assert "K40.rcspg: 2.12uSv in 43510s" in sys.stdout.getvalue()  # from the K40 spectrogram
    assert "not enough values to unpack" in sys.stderr.getvalue()  # from all the other test stuff
