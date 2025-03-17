#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import unittest
from os.path import dirname
from os.path import join as pathjoin

from radiacode_tools import rc_files  # type: ignore
from radiacode_tools.rc_types import SpectrumLayer  # type: ignore
from radiacode_tools.rc_utils import _BEGINNING_OF_TIME  # type: ignore

testdir = pathjoin(dirname(__file__), "data")


class TestRcFilesRcSpectrum(unittest.TestCase):
    "Testing the Spectrum interface"

    def test_rcspectrum(self):
        sp = rc_files.RcSpectrum()
        self.assertIsNotNone(str(sp))

        sp = rc_files.RcSpectrum(pathjoin(testdir, "data_th232_plus_background.xml"))
        self.assertIsNotNone(str(sp))
        self.assertIsNotNone(sp.as_dict())
        # self.assertIsNotNone(sp.uuid())
        self.assertEqual("2b06cd31-3519-2ca8-c6bb-698587cbe3d3", sp.uuid())
        self.assertAlmostEqual(153.2, sp.count_rate(), delta=0.1)
        self.assertAlmostEqual(3.5, sp.count_rate(bg=True), delta=0.1)
        sp.write_file("/dev/null")

    def test_rcspectrum_invalid(self):
        with self.assertRaises(ValueError):
            rc_files.RcSpectrum(pathjoin(testdir, "data_invalid_spectrum.xml"))

    def test_rcspectrum_incorrect_order(self):
        with self.assertRaises(ValueError):
            rc_files.RcSpectrum(pathjoin(testdir, "data_invalid_cal_incorrect_order.xml"))

    def test_rcspectrum_inconsistent(self):
        with self.assertRaises(ValueError):
            rc_files.RcSpectrum(pathjoin(testdir, "data_invalid_cal_inconsistent_order.xml"))


class TestRcFilesRcspg(unittest.TestCase):
    "Test the Spectrogram interface"

    def test_rcspg(self):
        spg = rc_files.RcSpectrogram(pathjoin(testdir, "K40.rcspg"))
        self.assertIsNotNone(spg.name)
        self.assertIsNotNone(str(spg))
        spg.write_file("/dev/null")

        spg2 = rc_files.RcSpectrogram()
        spg2.add_calibration(spg.calibration)
        # spg2.historical_spectrum = spg.historical_spectrum
        _ = [
            spg2.add_point(timestamp=s.datetime, counts=s.counts) for s in spg.samples if len(s.counts) == spg.channels
        ]
        self.assertGreater(len(spg2.samples), len(spg.samples) // 2)


class TestRcFilesRcTrack(unittest.TestCase):
    "Test the Track interface"

    def test_rctrk(self):
        tk = rc_files.RcTrack()
        tk.add_point(dt=_BEGINNING_OF_TIME, latitude=0.0, longitude=0.0, accuracy=1.0, dose_rate=1.0, count_rate=1.0)
        self.assertIsNotNone(str(tk))
        self.assertEqual(len(tk.points), 1)
        tk.write_file("/dev/null")

    def test_rctrk_dict_roundtrip(self):
        tk1 = rc_files.RcTrack(pathjoin(testdir, "walk.rctrk"))
        tk2 = rc_files.RcTrack()

        tk2.from_dict(tk1.as_dict())
        self.assertEqual(len(tk1.points), len(tk2.points))
        self.assertEqual(tk1.points[0].datetime.timestamp(), tk2.points[0].datetime.timestamp())

    def test_rctrk_bogus(self):
        tk = rc_files.RcTrack()
        with self.assertRaises(ValueError):
            tk.from_dict(dict())


class TestRcFilesN42(unittest.TestCase):
    "Test the N42 interface"

    def test_n42(self):
        n42 = rc_files.RcN42(pathjoin(testdir, "data_am241.n42"))
        self.assertIsNotNone(str(n42))

    def test_n42_from_spectrum(self):
        n42 = rc_files.RcN42()
        sp = rc_files.RcSpectrum(pathjoin(testdir, "data_th232_plus_background.xml"))
        n42.from_rcspectrum(sp)
        self.assertEqual(n42.serial_number, "RC-102-000115")
        self.assertEqual(n42.rad_detector_information["RadDetectorKindCode"], "CsI")
        self.assertEqual(n42.rad_instrument_information["RadInstrumentModelName"], "RadiaCode-102")
        self.assertIn("Radiacode-Tools", str(n42.rad_instrument_information["RadInstrumentVersion"]))

        s2 = n42.to_rcspectrum()
        self.assertEqual(sp.uuid(), s2.uuid())

        n42.write_file("/dev/null")

    def test_n42_invalid(self):
        with self.assertRaises(Exception):
            rc_files.RcN42(pathjoin(testdir, "data_invalid.n42"))

    def test_n42_creation_errors(self):
        thx = rc_files.RcSpectrum(pathjoin(testdir, "data_th232_plus_background.xml"))

        n42 = rc_files.RcN42()
        sp = rc_files.RcSpectrum()

        ### missing layer ###
        with self.assertRaises(AttributeError):
            n42.from_rcspectrum(sp)

        ### layer with no serial number ###
        sp.fg_spectrum = SpectrumLayer()
        with self.assertRaises(ValueError):
            n42.from_rcspectrum(sp)

        with self.assertRaises(ValueError):
            n42._populate_rad_instrument_information("")

        ### no calibration ###
        sp.fg_spectrum = SpectrumLayer(serial_number=thx.fg_spectrum.serial_number)
        n42.from_rcspectrum(sp)
        with self.assertRaises(TypeError):
            n42.write_file("/dev/null")

        ### no duration ###
        sp.fg_spectrum = SpectrumLayer(
            serial_number=thx.fg_spectrum.serial_number,
            calibration=thx.fg_spectrum.calibration,
        )
        n42.from_rcspectrum(sp)
        with self.assertRaises(AttributeError):
            n42.write_file("/dev/null")

        ### no timestamp ###
        sp.fg_spectrum = SpectrumLayer(
            serial_number=thx.fg_spectrum.serial_number,
            calibration=thx.fg_spectrum.calibration,
            duration=thx.fg_spectrum.duration,
        )
        n42.from_rcspectrum(sp)
        with self.assertRaises(AttributeError):
            n42.write_file("/dev/null")

        ### no counts ###
        sp.fg_spectrum = SpectrumLayer(
            serial_number=thx.fg_spectrum.serial_number,
            calibration=thx.fg_spectrum.calibration,
            duration=thx.fg_spectrum.duration,
            timestamp=thx.fg_spectrum.timestamp,
        )
        n42.from_rcspectrum(sp)
        with self.assertRaises(TypeError):
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
        self.assertIn("GaGG:Ce", buf)
        self.assertIsNone(n42.write_file("/dev/null"))
