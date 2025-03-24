#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

from os.path import dirname
from os.path import join as pathjoin
from unittest.mock import patch

import pytest

import recursive_deadtime as dtr

testdir = pathjoin(dirname(__file__), "data_deadtime")
bg = pathjoin(testdir, "bg.xml")


def test_get_args():
    with patch("sys.argv", [__file__, "-b", bg, testdir]):
        args = dtr.get_args()
        assert args.datadir == testdir
        assert args.bgfile == bg


def test_get_args_fail():
    with patch("sys.argv", [__file__, "--foobar"]):
        with pytest.raises(SystemExit):
            dtr.get_args()


def test_main_no_bg():
    with patch("sys.argv", [__file__, testdir]):
        assert dtr.main() is None


def test_main():
    with patch("sys.argv", [__file__, testdir, "-b", bg]):
        assert dtr.main() is None
