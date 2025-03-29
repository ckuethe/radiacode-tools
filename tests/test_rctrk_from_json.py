#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

from argparse import Namespace
from os.path import dirname
from os.path import join as pathjoin

import pytest

testdir = pathjoin(dirname(__file__), "data")
testfile = pathjoin(testdir, "broken_arrow_errrr_airplane.ndjson")

import rctrk_from_json
from radiacode_tools.rc_utils import _BEGINNING_OF_TIME


def test_missing_keys():
    want = ["apple", "orange"]
    tc_ok = ["apple", "orange", "peach"]
    tc_bad = ["apple", "banana", "peach"]
    assert rctrk_from_json.keys_missing(want, tc_ok) is False
    assert rctrk_from_json.keys_missing(want, tc_bad) is True


def test_argparse_no_args(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, "-o", ""])
    a = rctrk_from_json.get_args()
    assert a.input == "/dev/stdin"
    assert a.output == "/dev/stdout"


def test_argparse_default(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, "-i", testfile])
    a = rctrk_from_json.get_args()
    assert a.input == testfile


@pytest.mark.slow
def test_parts():
    args = Namespace(input=testfile, output=None, name="test", serial_number=None, comment=None)
    lines = rctrk_from_json.load_file_lines(args)
    trk = rctrk_from_json.convert_lines_to_track(args, lines)
    assert trk.name == "test"
    assert trk.timestamp > _BEGINNING_OF_TIME


@pytest.mark.slow
def test_main(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, "-i", testfile, "-o", "-"])
    assert rctrk_from_json.main() is None
