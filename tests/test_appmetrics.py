#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import unittest
from time import sleep

from radiacode_tools import appmetrics


class TestAppMetrics(unittest.TestCase):
    def test_stub(self):
        name = "foobar"
        amx = appmetrics.AppMetrics(stub=True, appname=name)

        d = amx.get_stats()
        self.assertEqual(d["process"]["appname"], name)
        self.assertGreater(d["process"]["pid"], 0)

        cv = 42
        cn = "a"
        amx.counter_create(cn, cv)
        self.assertEqual(d["counter"][cn], cv)
        amx.counter_increment(cn)
        self.assertEqual(d["counter"][cn], cv + 1)

        gn = "b"
        gv = 13
        amx.gauge_create(gn)
        self.assertEqual(d["gauge"][gn], 0)
        amx.gauge_update(gn, gv)
        self.assertEqual(d["gauge"][gn], gv)

        fn = "c"
        amx.flag_create(fn)
        self.assertFalse(d["flag"][fn])
        amx.flag_set(fn)
        self.assertTrue(d["flag"][fn])
        amx.flag_clear(fn)
        self.assertFalse(d["flag"][fn])

        sleep(0.1)
        b = amx.get_stats()
        self.assertEqual(d["process"]["pid"], b["process"]["pid"])
        # self.assertLess(d["process"]["real"], b["process"]["real"])

    def test_errors(self):
        name = "foobar"
        amx = appmetrics.AppMetrics(stub=True, appname=name)

        cn = "a"
        amx.counter_create(cn)
        with self.assertRaises(ValueError):  # already exists
            amx.counter_create(cn)
        with self.assertRaises(KeyError):  # doesn't exist
            amx.counter_decrement("x")

        gn = "b"
        amx.gauge_create(gn)
        with self.assertRaises(ValueError):  # already exists
            amx.gauge_create(gn)
        with self.assertRaises(KeyError):  # doesn't exist
            amx.gauge_update("x", 0)

        fn = "c"
        amx.flag_create(fn)
        with self.assertRaises(ValueError):  # already exists
            amx.flag_create(fn)
        with self.assertRaises(KeyError):  # doesn't exist
            amx.flag_setval("x", True)

        with self.assertRaises(ValueError):
            amx._create_metric("invalid", "foo", None)
