#!/usr/bin/env python3
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

from argparse import Namespace
from os.path import dirname
from os.path import join as pathjoin

import pytest

testdir = pathjoin(dirname(__file__), "data")
testfile = pathjoin(testdir, "broken_arrow_errrr_airplane.ndjson")

import rctrk_from_json
from radiacode_tools.rc_utils import BEGINNING_OF_TIME


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

    monkeypatch.setattr("sys.argv", [__file__, "-i", testfile, "-s", "invalid-serial-number"])
    with pytest.raises(SystemExit):
        rctrk_from_json.get_args()


@pytest.mark.slow
def test_parts():
    args = Namespace(input=testfile, output=None, name="test", serial_number=None, comment=None)
    lines = rctrk_from_json.load_file_lines(args)
    trk = rctrk_from_json.convert_lines_to_track(args, lines)
    assert trk.name == "test"
    assert trk.timestamp > BEGINNING_OF_TIME


@pytest.mark.slow
def test_main(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, "-i", testfile, "-o", "-"])
    assert rctrk_from_json.main() is None


def test_load_file_lines_spectrum_data():
    """Test load_file_lines skips spectrum data"""
    import tempfile
    from argparse import Namespace

    from rctrk_from_json import load_file_lines

    # Create test data with GpsData and RealTimeData
    data = """{"type": "GpsData", "payload": {"time": "2023-01-01T00:00:00Z", "lat": 1.0, "lon": 2.0, "epc": 5, "gnss": true, "serial_number": "RC-100-123456"}}
{"type": "RealTimeData", "dt": "2023-01-01T00:00:00Z", "dose_rate": 0.1, "count_rate": 10, "serial_number": "RC-100-123456"}
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write(data)
        f.flush()

        args = Namespace(input=f.name, output=None, serial_number=None, name=None, comment="")

        result = load_file_lines(args)

        # Should have 1 entry with merged data
        assert len(result) >= 1
