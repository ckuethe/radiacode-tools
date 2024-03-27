#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT


import os
import unittest
from os.path import dirname
from os.path import join as pathjoin
from tempfile import mkstemp
from unittest.mock import patch

import n42validate

testdir = pathjoin(dirname(__file__), "data")


class TestN42Validate(unittest.TestCase):
    schema_file = pathjoin(testdir, "n42.xsd")
    n42_file = pathjoin(testdir, "data_am241.n42")
    bad_file = pathjoin(testdir, "data_invalid.n42")

    def test_schema_load(self):
        schema = n42validate.fetch_or_load_xsd(schema_file=self.schema_file)
        self.assertIsNotNone(schema)

    def test_schema_fetch(self):
        with open(self.schema_file, "r") as fd:
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
            self.assertIsNotNone(schema)
            os.unlink(tfn)

    def test_schema_fetch_fail(self):
        def mocked_requests_get(*args, **kwargs):
            class MockResponse:
                def __init__(self):
                    self.status_code = 500
                    self.ok = False
                    self.text = ""

            return MockResponse()

        with patch("requests.get", mocked_requests_get):
            with self.assertRaises(RuntimeError):
                n42validate.fetch_or_load_xsd(schema_file="./nonexistent")

    def test_argparse_fail(self):
        with self.assertRaises(SystemExit):
            n42validate.get_args()

    def test_argparse(self):
        with patch("sys.argv", [__file__, "-s", self.schema_file, self.n42_file]):
            parsed_args = n42validate.get_args()
            self.assertEqual(parsed_args.schema_file, self.schema_file)
            self.assertEqual(parsed_args.files, [self.n42_file])

    def test_single(self):
        with patch("sys.argv", [__file__, "-s", self.schema_file, "--verbose", self.n42_file]):
            n42validate.main()

    def test_single_xml_fail(self):
        with self.assertRaises(n42validate.ET.ParseError):
            with patch("sys.argv", [__file__, "-s", self.schema_file, "--valid-only", "/dev/null"]):
                n42validate.main()

    def test_single_invalid(self):
        with patch("sys.argv", [__file__, "-s", self.schema_file, self.bad_file]):
            n42validate.main()

    def test_main_recursive(self):
        with patch("sys.argv", [__file__, "-s", self.schema_file, "--recursive", "--valid-only", "--verbose", testdir]):
            n42validate.main()

    def test_main_recursive_quiet(self):
        with patch("sys.argv", [__file__, "-s", self.schema_file, "--recursive", "--quiet", testdir]):
            n42validate.main()
