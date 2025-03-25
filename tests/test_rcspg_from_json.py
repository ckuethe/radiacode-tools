#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

from os.path import dirname
from os.path import join as pathjoin

import pytest

testdir = pathjoin(dirname(__file__), "data")
testfile = pathjoin(testdir, "xray.ndjson")

import rcspg_from_json


def test_argparse_no_args(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, "-o", ""])
    a = rcspg_from_json.get_args()
    assert a.input == "/dev/stdin"
    assert a.output == "/dev/stdout"


def test_argparse_default(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, "-i", testfile])
    a = rcspg_from_json.get_args()
    assert a.input == testfile


@pytest.mark.slow
def test_main(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, "-i", testfile, "-o", "-"])
    assert rcspg_from_json.main() is None
