#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import unittest
from os.path import dirname
from os.path import join as pathjoin

import pytest

import n42www
from n42www import n42srv

testdir = pathjoin(dirname(__file__), "data")


class TestN42Www(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = n42srv.app_context()
        self.ctx.push()
        self.client = n42srv.test_client()

    def tearDown(self) -> None:
        self.ctx.pop()

    def test_index(self):
        p = n42www.handle_index()
        self.assertIn("Radiacode", p)

    def test_convert(self):
        fn = "data_am241.xml"
        dfn = f"filename={fn.replace('xml', 'n42')}"
        with open(pathjoin(testdir, fn), "rb") as am241:
            response = self.client.post("/convert", data={"file-input": (am241, fn)})
            self.assertEqual(response.status_code, 200)
            self.assertIn(dfn, str(response.headers))
            self.assertIn(
                'radDetectorInformationReference="radiacode-scinitillator-sipm"', response.get_data(as_text=True)
            )

    def test_convert_bad_field(self):
        fn = "data_am241.xml"
        with open("/dev/null", "rb") as am241:
            response = self.client.post("/convert", data={"file-name": (am241, fn)})
            self.assertEqual(response.status_code, 400)

    def test_convert_bad_fcontent(self):
        fn = "data_am241.xml"
        with open("/dev/null", "rb") as am241:
            response = self.client.post("/convert", data={"file-input": (am241, fn)})
            self.assertEqual(response.status_code, 400)


def test_main(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, "-vvv", "-b", "255.255.255.255", "-p", "1"])
    with pytest.raises(SystemExit):
        n42www.main()
    monkeypatch.setattr("sys.argv", [__file__, "-v", "-b", "255.255.255.255", "-p", "1"])
    with pytest.raises(SystemExit):
        n42www.main()
    monkeypatch.setattr("sys.argv", [__file__, "-b", "255.255.255.255", "-p", "1"])
    with pytest.raises(SystemExit):
        n42www.main()


def test_argparse_invalid_port(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, "-p", "1000000"])
    with pytest.raises(SystemExit):
        n42www.get_args()


def test_argparse_no_args(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__])
    parsed_args = n42www.get_args()
    assert parsed_args.bind_addr == "127.0.0.1"
    assert parsed_args.port == 6853
    assert parsed_args.max_size == 128 * 1024


def test_argparse_has_args(monkeypatch):
    addr = "0.0.0.0"
    port = 4242
    size = 160000
    monkeypatch.setattr("sys.argv", [__file__, "-b", addr, "-p", str(port), "-m", str(size), "-vvv"])
    parsed_args = n42www.get_args()
    assert parsed_args.bind_addr == addr
    assert parsed_args.port == port
    assert parsed_args.max_size == size
    assert parsed_args.verbose == 3
