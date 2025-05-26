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

test_dir: str = pathjoin(dirname(__file__), "data")


header_fields: list[str] = [
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
    assert "while processing" in sys.stderr.getvalue()  # from all the other test stuff
