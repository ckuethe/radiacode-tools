#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import deadtime
import unittest
from unittest.mock import patch
from io import StringIO
from os.path import dirname, join as pathjoin
from typing import Dict, Any


testdir = dirname(__file__)


class TestDeadTime(unittest.TestCase):
    a = pathjoin(testdir, "test_dt_ba133.xml")
    b = pathjoin(testdir, "test_dt_na22.xml")
    c = pathjoin(testdir, "test_dt_ba133_na22.xml")
    g = pathjoin(testdir, "test_dt_bg.xml")

    # More work needs to be done to understand the behavior of the scintillator with varying
    # fluxes. Dead time is nonlinear, but how non-linear? Does it depend on absorbed dose?
    # These measurements used two 1uCi sources, 72mm away from the detector, on a granite
    # surface.
    r_Ba = 1849708 / 300
    r_Ba_Eu = 2720349 / 300
    r_bg = 16832 / 3903
    r_Eu = 1075972 / 300
    dt_w_bg = 16.66e-6
    dt_no_bg = 16.75e-6

    def test_get_args(self):
        with patch("sys.argv", [__file__, "-a", self.a, "-b", self.b, "-c", self.c, "-g", self.g]):
            args = deadtime.get_args()
            self.assertEqual(args.first, self.a)
            self.assertEqual(args.second, self.b)
            self.assertEqual(args.combined, self.c)
            self.assertEqual(args.background, self.g)

        count_rates = deadtime.load_spectra(args)
        self.assertIn("bg", count_rates)
        dt = deadtime.compute_deadtime(count_rates)
        self.assertAlmostEqual(dt, 2.635e-3, delta=1e-5)

    def test_get_args_nobg(self):
        with patch("sys.argv", [__file__, "-a", self.a, "-b", self.b, "-c", self.c]):
            args = deadtime.get_args()
            self.assertEqual(args.first, self.a)
            self.assertEqual(args.second, self.b)
            self.assertEqual(args.combined, self.c)
            self.assertIsNone(args.background)

        count_rates = deadtime.load_spectra(args)
        self.assertEqual(0, count_rates["bg"])
        dt = deadtime.compute_deadtime(count_rates)
        self.assertAlmostEqual(dt, 66.28e-6, delta=1e-5)

    def test_get_args_fail(self):
        with patch("sys.argv", [__file__, "-a", self.a, "-b", self.b, "-g", self.g]):
            with self.assertRaises(SystemExit):
                deadtime.get_args()

    def test_compute_tau_nobg(self):
        dt = deadtime.compute_tau(self.r_Ba, self.r_Eu, self.r_Ba_Eu)
        self.assertAlmostEqual(dt, self.dt_no_bg, delta=1e-4)

    def test_compute_tau(self):
        dt = deadtime.compute_tau(self.r_Ba, self.r_Eu, self.r_Ba_Eu, self.r_bg)
        self.assertAlmostEqual(dt, self.dt_w_bg, delta=1e-4)

    def test_compute_tau_bg_fail(self):
        with self.assertRaises(ValueError) as cm:
            deadtime.compute_tau(100, 100, 190, -1)
        self.assertIn("negative", cm.exception.args[0])

    def test_compute_tau_fg_fail(self):
        with self.assertRaises(ValueError) as cm:
            deadtime.compute_tau(0, 1, 1, 0)
        self.assertIn("zero", cm.exception.args[0])

    def test_compute_loss(self):
        data = {"a": self.r_Ba, "b": self.r_Eu, "ab": self.r_Ba_Eu, "bg": self.r_bg}
        lf = deadtime.compute_loss(data)
        self.assertAlmostEqual(lf, 0.07, delta=1e-3)

    def test_main(self):
        with patch("sys.argv", [__file__, "-a", self.a, "-b", self.b, "-c", self.c, "-g", self.g]):
            self.assertIsNone(deadtime.main())
