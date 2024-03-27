#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import json
import os
import unittest
from argparse import Namespace
from tempfile import mkstemp
from unittest.mock import patch

import calibrate


class TestCalibrate(unittest.TestCase):
    def test_argparse_fail(self):
        with patch("sys.argv", [__file__, "-o", "-1"]):
            with self.assertRaises(SystemExit):
                calibrate.get_args()

    def test_argparse_fail2(self):
        with patch("sys.argv", [__file__, "-o", "2.5"]):
            with self.assertRaises(SystemExit):
                calibrate.get_args()

    def test_argparse(self):
        with patch("sys.argv", [__file__, "-o", "2"]):
            parsed_args = calibrate.get_args()
            self.assertEqual(parsed_args.order, 2)

    def test_load_calibration_devnull_fail(self):
        args = Namespace(cal_file="/dev/null")
        with self.assertRaises(json.decoder.JSONDecodeError):
            calibrate.load_calibration(args)

    def test_cal_file_unconfigured_fail(self):
        fd, cal_file = mkstemp(prefix="pytest")
        os.close(fd)
        args = Namespace(cal_file=cal_file)
        with self.assertRaises(SystemExit):
            # template_calibration exits
            calibrate.template_calibration(args=args)

        with self.assertRaises(TypeError):
            calibrate.load_calibration(args)

        os.unlink(cal_file)

    def test_cal_file(self):
        fd, cal_file = mkstemp(prefix="pytest")
        os.close(fd)
        args = Namespace(cal_file=cal_file, order=2, precision=8, zero_start=True)
        with self.assertRaises(SystemExit):
            # template_calibration exits
            calibrate.template_calibration(args=args)

        s1 = os.path.getsize(cal_file)
        self.assertGreater(s1, 1024)

        with open(cal_file) as fd:
            cal = json.load(fd)

        u = "unobtainium"
        self.assertIn(u, cal)
        cal.pop(u)
        self.assertNotIn(u, cal)

        with open(cal_file, "w") as fd:
            json.dump(cal, fd)
        s2 = os.path.getsize(cal_file)
        self.assertLess(s2, s1)

        cal = calibrate.load_calibration(args)

        chan, energy = zip(*cal)
        expected_fit = [1.11173792, 2.77390428, 3.66e-06]
        expected_rsq = 1.0

        pf = calibrate.make_fit(chan, energy, args)
        self.assertEqual(calibrate.make_fit(chan, energy, args), expected_fit)

        rsq = calibrate.rsquared(chan, energy, pf)
        self.assertAlmostEqual(rsq, expected_rsq, delta=0.0001)

        with patch("sys.argv", [__file__, "-f", cal_file]):
            self.assertIsNone(calibrate.main())

        os.unlink(cal_file)

    def test_main_file(self):
        with self.assertRaises(SystemExit):
            with patch("sys.argv", [__file__, "-f", "/dev/null"]):
                calibrate.main()
        with self.assertRaises(SystemExit):
            with patch("sys.argv", [__file__, "-f", "./nonexistent"]):
                calibrate.main()
