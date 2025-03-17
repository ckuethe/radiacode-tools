#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import unittest

from radiacode_tools import rc_types


class TestRcTypes(unittest.TestCase):
    def test_rangefinder(self):
        l = [42, 65536, 0o105, 0xFF, -1, 0]
        rf = rc_types.RangeFinder()
        rf.add(l)
        self.assertEqual((min(l), max(l)), rf.get())
        self.assertIn(str(max(l)), str(rf))
        self.assertIsNone(rf.__repr__())
