#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import unittest
from os.path import dirname
from os.path import join as pathjoin
from unittest.mock import patch

import deadtime

testdir = pathjoin(dirname(__file__), "data_deadtime")


class TestDeadTime(unittest.TestCase):
    f_a = pathjoin(testdir, "Ba133_Eu152", "Ba133_a.xml")
    f_b = pathjoin(testdir, "Ba133_Eu152", "Eu152_b.xml")
    f_ab = pathjoin(testdir, "Ba133_Eu152", "Ba133_a+Eu152_b.xml")
    f_bg = pathjoin(testdir, "bg.xml")

    # More work needs to be done to understand the behavior of the scintillator with varying
    # fluxes. Dead time is nonlinear, but how non-linear? Does it depend on absorbed dose?
    # These measurements used two 1uCi sources, 72mm away from the detector, on a granite
    # surface.
    r_Ba = 1849708 / 300
    r_Ba_Eu = 2720349 / 300
    r_bg = 16832 / 3903
    r_Eu = 1075972 / 300
    expected_dt_w_bg = 16.66e-6
    expected_dt_no_bg = 16.75e-6
    expected_lost_cps = 684
    expected_loss_fraction = 0.07

    def test_get_args(self):
        "does get_args() work?"
        with patch("sys.argv", [__file__, "-a", self.f_a, "-b", self.f_b, "-c", self.f_ab, "-g", self.f_bg]):
            args = deadtime.get_args()
            self.assertEqual(args.first, self.f_a)
            self.assertEqual(args.second, self.f_b)
            self.assertEqual(args.combined, self.f_ab)
            self.assertEqual(args.background, self.f_bg)

            # Also check that file vs float input works
            rates = deadtime.load_spectra(args)
            # Right now, I don't care how much greater than zero
            self.assertGreater(rates["a"], 0)
            self.assertGreater(rates["b"], 0)
            self.assertGreater(rates["ab"], 0)
            self.assertGreater(rates["bg"], 0)

    def test_get_args_nobg(self):
        "does get_args() correctly handle no background?"
        with patch("sys.argv", [__file__, "-a", self.f_a, "-b", self.f_b, "-c", self.f_ab]):
            args = deadtime.get_args()
            self.assertEqual(args.first, self.f_a)
            self.assertEqual(args.second, self.f_b)
            self.assertEqual(args.combined, self.f_ab)
            self.assertIsNone(args.background)

    def test_get_args_numeric(self):
        with patch(
            "sys.argv",
            [__file__, "-a", f"{self.r_Ba}", "-b", f"{self.r_Eu}", "-c", f"{self.r_Ba_Eu}", "-g", f"{self.r_bg}"],
        ):
            args = deadtime.get_args()
            self.assertAlmostEqual(float(args.first), self.r_Ba)
            self.assertAlmostEqual(float(args.second), self.r_Eu)
            self.assertAlmostEqual(float(args.combined), self.r_Ba_Eu)
            self.assertAlmostEqual(float(args.background), self.r_bg)

        count_rates = deadtime.load_spectra(args)
        dt = deadtime.compute_deadtime(**count_rates)
        self.assertAlmostEqual(dt.dt_us, self.expected_dt_w_bg, delta=1e-5)

    def test_get_args_numeric_nobg(self):
        with patch(
            "sys.argv",
            [__file__, "-a", f"{self.r_Ba}", "-b", f"{self.r_Eu}", "-c", f"{self.r_Ba_Eu}"],
        ):
            args = deadtime.get_args()

        count_rates = deadtime.load_spectra(args)
        dt = deadtime.compute_deadtime(**count_rates)
        self.assertAlmostEqual(dt.dt_us, self.expected_dt_no_bg, delta=1e-5)
        self.assertAlmostEqual(dt.loss_fraction, self.expected_loss_fraction, delta=1e-3)
        self.assertAlmostEqual(dt.lost_cps, self.expected_lost_cps, delta=0.5)

    def test_get_args_fail(self):
        with patch("sys.argv", [__file__, "-a", self.f_a, "-b", self.f_b, "-g", self.f_bg]):
            with self.assertRaises(SystemExit):
                deadtime.get_args()

    def test_compute_deadtime_bg_fail(self):
        with self.assertRaises(ValueError) as cm:
            deadtime.compute_deadtime(a=100, b=100, ab=190, bg=-1)
        self.assertIn("negative", cm.exception.args[0])

    def test_compute_deadtime_fg_fail(self):
        with self.assertRaises(ValueError) as cm:
            deadtime.compute_deadtime(a=0, b=1, ab=1, bg=0)
        self.assertIn("zero", cm.exception.args[0])

    def test_main(self):
        with patch(
            "sys.argv",
            [__file__, "-a", f"{self.r_Ba}", "-b", f"{self.r_Eu}", "-c", f"{self.r_Ba_Eu}", "-g", f"{self.r_bg}"],
        ):
            self.assertIsNone(deadtime.main())
