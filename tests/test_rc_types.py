#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

from radiacode_tools import rc_types


def test_rangefinder():
    l = [42, 65536, 0o105, 0xFF, -1, 0]
    rf = rc_types.RangeFinder()
    rf.add(l)
    assert rf.get() == (min(l), max(l))
    assert str(max(l)) in str(rf)
    assert rf.__repr__() is None
