#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import recursive_deadtime as dtr
import unittest
from unittest.mock import patch
from os.path import dirname, join as pathjoin


testdir = pathjoin(dirname(__file__), "data_deadtime")


class TestDeadTime(unittest.TestCase):
    bg = pathjoin(testdir, "bg.xml")

    def test_get_args(self):
        with patch("sys.argv", [__file__, "-b", self.bg, testdir]):
            args = dtr.get_args()
            self.assertEqual(args.datadir, testdir)
            self.assertEqual(args.bgfile, self.bg)

    def test_get_args_fail(self):
        with patch("sys.argv", [__file__, "--foobar"]):
            with self.assertRaises(SystemExit):
                dtr.get_args()

    def test_main_no_bg(self):
        with patch("sys.argv", [__file__, testdir]):
            self.assertIsNone(dtr.main())

    def test_main(self):
        with patch("sys.argv", [__file__, testdir, "-b", self.bg]):
            self.assertIsNone(dtr.main())
