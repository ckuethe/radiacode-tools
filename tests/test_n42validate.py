#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT


import os
from os.path import dirname
from os.path import join as pathjoin
from tempfile import mkstemp
from unittest.mock import patch

import pytest

import n42validate

testdir = pathjoin(dirname(__file__), "data")


schema_file = pathjoin(testdir, "n42.xsd")
n42_file = pathjoin(testdir, "data_am241.n42")
bad_file = pathjoin(testdir, "data_invalid.n42")


@pytest.mark.slow
def test_schema_load():
    schema = n42validate.fetch_or_load_xsd(schema_file=schema_file)
    assert schema


@pytest.mark.slow
def test_schema_fetch():
    with open(schema_file, "r") as fd:
        schema_text = fd.read()

    def mocked_requests_get(*args, **kwargs):
        class MockResponse:
            def __init__(self):
                self.status_code = 200
                self.ok = True
                self.text = schema_text

        return MockResponse()

    with patch("requests.get", mocked_requests_get):
        tfd, tfn = mkstemp(prefix="pytest_schema_fetch_")
        os.close(tfd)
        schema = n42validate.fetch_or_load_xsd(schema_file=tfn)
        assert schema
        os.unlink(tfn)


def test_schema_fetch_fail():
    def mocked_requests_get(*args, **kwargs):
        class MockResponse:
            def __init__(self):
                self.status_code = 500
                self.ok = False
                self.text = ""

        return MockResponse()

    with patch("requests.get", mocked_requests_get):
        with pytest.raises(RuntimeError):
            n42validate.fetch_or_load_xsd(schema_file="./nonexistent")


def test_argparse_fail():
    with pytest.raises(SystemExit):
        n42validate.get_args()


def test_argparse():
    with patch("sys.argv", [__file__, "-s", schema_file, n42_file]):
        parsed_args = n42validate.get_args()
        assert parsed_args.schema_file == schema_file
        assert parsed_args.files == [n42_file]


@pytest.mark.slow
def test_single():
    with patch("sys.argv", [__file__, "-s", schema_file, "--verbose", n42_file]):
        n42validate.main()


@pytest.mark.slow
def test_single_xml_fail():
    with pytest.raises(n42validate.ET.ParseError):
        with patch("sys.argv", [__file__, "-s", schema_file, "--valid-only", "/dev/null"]):
            n42validate.main()


@pytest.mark.slow
def test_single_invalid():
    with patch("sys.argv", [__file__, "-s", schema_file, bad_file]):
        n42validate.main()


@pytest.mark.slow
def test_main_recursive():
    with patch("sys.argv", [__file__, "-s", schema_file, "--recursive", "--valid-only", "--verbose", testdir]):
        n42validate.main()


@pytest.mark.slow
def test_main_recursive_quiet():
    with patch("sys.argv", [__file__, "-s", schema_file, "--recursive", "--quiet", testdir]):
        n42validate.main()
