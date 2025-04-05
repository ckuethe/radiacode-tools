#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

from os.path import dirname
from os.path import join as pathjoin

import pytest

from radiacode_tools.rc_files import RcN42, RcSpectrum
from radiacode_tools.rc_types import SpectrumLayer

testdir = pathjoin(dirname(__file__), "data")


def test_n42():
    n42 = RcN42(pathjoin(testdir, "data_am241.n42"))
    assert str(n42)


def test_n42_from_spectrum():
    n42 = RcN42()
    sp = RcSpectrum(pathjoin(testdir, "data_th232_plus_background.xml"))
    n42.from_rcspectrum(sp)
    assert n42.serial_number == "RC-102-000115"
    assert n42.rad_detector_information["RadDetectorKindCode"] == "CsI"
    assert n42.rad_instrument_information["RadInstrumentModelName"] == "RadiaCode-102"
    assert "Radiacode-Tools" in str(n42.rad_instrument_information["RadInstrumentVersion"])

    s2 = n42.to_rcspectrum()
    assert sp.uuid() == s2.uuid()

    n42.write_file("/dev/null")


def test_n42_invalid():
    with pytest.raises(Exception):
        RcN42(pathjoin(testdir, "data_invalid.n42"))


def test_n42_creation_errors():
    thx = RcSpectrum(pathjoin(testdir, "data_th232_plus_background.xml"))

    n42 = RcN42()
    sp = RcSpectrum()

    ### missing layer ###
    with pytest.raises(AttributeError):
        n42.from_rcspectrum(sp)

    ### layer with no serial number ###
    sp.fg_spectrum = SpectrumLayer()
    with pytest.raises(ValueError):
        n42.from_rcspectrum(sp)

    with pytest.raises(ValueError):
        n42._populate_rad_instrument_information("")

    ### no calibration ###
    sp.fg_spectrum = SpectrumLayer(
        serial_number=thx.fg_spectrum.serial_number, timestamp=thx.fg_spectrum.timestamp, calibration=None
    )
    n42.from_rcspectrum(sp)
    with pytest.raises(ValueError, match="foreground calibration"):
        n42.write_file("/dev/null")

    ### no duration ###
    sp.fg_spectrum = SpectrumLayer(
        serial_number=thx.fg_spectrum.serial_number,
        timestamp=thx.fg_spectrum.timestamp,
        calibration=thx.fg_spectrum.calibration,
        duration=None,
    )
    n42.from_rcspectrum(sp)
    with pytest.raises(AttributeError, match="total_seconds"):
        n42.write_file("/dev/null")

    ### no timestamp ###
    sp.fg_spectrum = SpectrumLayer(
        serial_number=thx.fg_spectrum.serial_number,
        calibration=thx.fg_spectrum.calibration,
        duration=thx.fg_spectrum.duration,
        counts=[1],
    )
    n42.from_rcspectrum(sp)
    with pytest.raises(ValueError, match="spectrum layer has no timestamp"):
        n42.write_file("/dev/null")

    ### no counts ###
    sp.fg_spectrum = SpectrumLayer(
        serial_number=thx.fg_spectrum.serial_number,
        calibration=thx.fg_spectrum.calibration,
        duration=thx.fg_spectrum.duration,
        timestamp=thx.fg_spectrum.timestamp,
    )
    n42.from_rcspectrum(sp)
    with pytest.raises(ValueError, match="spectrum layer has no counts"):
        n42.write_file("/dev/null")

    ### Success! ###
    sp.fg_spectrum = SpectrumLayer(
        serial_number=thx.fg_spectrum.serial_number.replace("RC-102", "RC-103G"),
        calibration=thx.fg_spectrum.calibration,
        duration=thx.fg_spectrum.duration,
        timestamp=thx.fg_spectrum.timestamp,
        counts=thx.fg_spectrum.counts,
    )
    n42.from_rcspectrum(sp)
    buf = n42.generate_xml()
    assert "GaGG:Ce" in buf
    assert n42.write_file("/dev/null") is None
