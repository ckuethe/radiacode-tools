#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import unittest
from datetime import datetime
from os.path import dirname
from os.path import join as pathjoin
from unittest.mock import patch

testdir = pathjoin(dirname(__file__), "data")
testfile = pathjoin(testdir, "xray.ndjson")

import rcspg_from_json


class TestRcspgJson(unittest.TestCase):
    def test_argparse_no_args(self):
        with patch("sys.argv", [__file__, "-o", ""]):
            a = rcspg_from_json.get_args()
            self.assertEqual(a.input, "/dev/stdin")
            self.assertEqual(a.output, "/dev/stdout")

    def test_argparse_default(self):
        with patch("sys.argv", [__file__, "-i", testfile]):
            a = rcspg_from_json.get_args()
            self.assertEqual(a.input, testfile)

    def test_main(self):
        with patch("sys.argv", [__file__, "-i", testfile, "-o", "-"]):
            rcspg_from_json.main()
