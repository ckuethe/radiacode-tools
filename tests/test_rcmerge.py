#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import json

import pytest

import rcmerge

SERIAL = "RC-103-000070"
NCH = 8


def _iso(epoch):
    from datetime import datetime, timezone

    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()


def _spec(monotime, dt, counts, duration=5.0):
    return {
        "dt": _iso(dt),
        "monotime": monotime,
        "serial_number": SERIAL,
        "spectrum": {
            "duration": duration,
            "a0": 1.0,
            "a1": 2.0,
            "a2": 3.0,
            "counts": counts,
            "_dataclass": True,
            "_type": "Spectrum",
        },
        "_dataclass": True,
        "_type": "SpecData",
    }


def _rt(monotime, dt, type="RealTimeData"):
    return {
        "dt": _iso(dt),
        "monotime": monotime,
        "serial_number": SERIAL,
        "type": type,
        "_dataclass": True,
        "_type": "RtData",
    }


def _gps(monotime, ts):
    return {
        "monotime": monotime,
        "payload": {"time": _iso(ts), "gnss": True, "mode": 3},
        "_dataclass": True,
        "_type": "GpsData",
    }


def _write(tmp_path, name, records):
    p = tmp_path / name
    with open(p, "w") as fd:
        for rec in records:
            print(json.dumps(rec), file=fd)
    return str(p)


def _session_a(real0=1000.0):
    "One recording session: accumulated, zeros, then a few samples"
    return [
        _spec(10.0, real0, [5, 5, 5], duration=100.0),  # line1: accumulated snapshot
        _spec(10.5, real0 + 0.5, [0, 0, 0], duration=0.0),  # line2: incremental zeros
        _gps(11.0, real0 + 1.0),
        _rt(11.5, real0 + 1.5),
        _spec(12.0, real0 + 2.0, [1, 0, 0]),
        _rt(12.5, real0 + 2.5),
        _spec(13.0, real0 + 3.0, [2, 0, 1]),
    ]


def _session_b(real0=5000.0):
    "A second session after a host reboot (monotime resets to ~0)"
    return [
        _spec(3.0, real0, [0, 0, 0], duration=0.0),  # accumulated resets to zero
        _spec(3.5, real0 + 0.5, [0, 0, 0], duration=0.0),
        _gps(4.0, real0 + 1.0),
        _spec(5.0, real0 + 2.0, [1, 1, 1]),
        _rt(5.5, real0 + 2.5),
    ]


def test_validate_ok(tmp_path):
    a = _session_a()
    b = _session_b()
    paths = [
        _write(tmp_path, f"raw_{SERIAL}_20260101000000.ndjson", a),
        _write(tmp_path, f"raw_{SERIAL}_20260101010000.ndjson", b),
    ]
    files = [rcmerge._read_file(p) for p in paths]
    assert rcmerge._validate(paths, files) == SERIAL


def test_validate_filename_serial_mismatch(tmp_path):
    p = _write(tmp_path, "raw_RC-999-999999_20260101000000.ndjson", _session_a())
    with pytest.raises(ValueError, match="serial"):
        rcmerge._validate([p], [rcmerge._read_file(p)])


def test_validate_filename_no_serial(tmp_path):
    p = _write(tmp_path, "log.ndjson", _session_a())
    with pytest.raises(ValueError, match="no radiacode serial"):
        rcmerge._validate([p], [rcmerge._read_file(p)])


def test_validate_multiple_devices(tmp_path):
    pa = _write(tmp_path, f"raw_{SERIAL}_20260101000000.ndjson", _session_a())
    other = json.loads(json.dumps(_session_a()))
    for rec in other:
        if rec["_type"] == "SpecData":
            rec["serial_number"] = "RC-101-111111"
    pb = _write(tmp_path, "raw_RC-101-111111_20260101000000.ndjson", other)
    with pytest.raises(ValueError, match="multiple devices"):
        rcmerge._validate([pa, pb], [rcmerge._read_file(pa), rcmerge._read_file(pb)])


def test_build_output_sums_spectra(tmp_path):
    a = _session_a()
    b = _session_b()
    paths = [
        _write(tmp_path, f"raw_{SERIAL}_20260101000000.ndjson", a),
        _write(tmp_path, f"raw_{SERIAL}_20260101010000.ndjson", b),
    ]
    files = [rcmerge._read_file(p) for p in paths]
    out = rcmerge._build_output(SERIAL, files)

    # line 1 is the total accumulated spectrum
    line1 = out[0]
    assert line1["_type"] == "SpecData"
    counts = line1["spectrum"]["counts"]
    # total = every SpecData summed: a's [5,5,5],[0,0,0],[1,0,0],[2,0,1]
    # plus b's [0,0,0],[0,0,0],[1,1,1]
    assert counts == [9, 6, 7]

    # line 2 is all zeros
    assert out[1]["spectrum"]["counts"] == [0, 0, 0]

    # monotime is monotonic across the whole stream (handles the reboot)
    mt = [rec["monotime"] for rec in out[2:]]
    assert mt == sorted(mt)
    # first session's monotime is preserved
    assert out[2]["monotime"] == 10.5
    # last record comes after the rebooted session starts
    assert mt[-1] > mt[0]


def test_build_output_rebase_across_reboot(tmp_path):
    a = _session_a(real0=1000.0)
    b = _session_b(real0=5000.0)
    paths = [
        _write(tmp_path, f"raw_{SERIAL}_20260101000000.ndjson", a),
        _write(tmp_path, f"raw_{SERIAL}_20260101010000.ndjson", b),
    ]
    files = [rcmerge._read_file(p) for p in paths]
    out = rcmerge._build_output(SERIAL, files)

    mt = [rec["monotime"] for rec in out[2:]]
    # session a ends at monotime 13; session b's first record (gps at monotime 4)
    # must be stitched after session a's last record
    assert mt[-1] > mt[-2]
    # the gap should reflect the GNSS real-time gap between the sessions (4000s),
    # not the raw monotime reset
    assert (mt[-1] - mt[0]) > 3000


def test_build_output_inserts_bridge(tmp_path):
    # file a: accumulated S=[10,0,0], per-sample increments Si_a=[0,0,0]
    a = [
        _spec(1.0, 1000.0, [10, 0, 0], duration=100.0),
        _spec(6.0, 1005.0, [0, 0, 0]),
    ]
    # file b: accumulated S=[15,5,0] (grew by 5,5,0 over the gap), Si_b=[1,0,0]
    b = [
        _spec(2.0, 5000.0, [15, 5, 0], duration=0.0),
        _spec(7.0, 5005.0, [1, 0, 0]),
    ]
    paths = [
        _write(tmp_path, f"raw_{SERIAL}_20260101000000.ndjson", a),
        _write(tmp_path, f"raw_{SERIAL}_20260101010000.ndjson", b),
    ]
    files = [rcmerge._read_file(p) for p in paths]
    out = rcmerge._build_output(SERIAL, files)

    # bridge = clamp(S_b - (S_a + Si_a), 0) = clamp([15,5,0]-[10,0,0], 0) = [5,5,0]
    # total = S_a + Si_a + Si_b + bridge = [10,0,0]+[0,0,0]+[1,0,0]+[5,5,0] = [16,5,0]
    assert out[0]["spectrum"]["counts"] == [16, 5, 0]
    # the bridge spectrum appears in the stream with the gap counts
    spec_stream = [rec for rec in out[2:] if rec["_type"] == "SpecData"]
    assert any(rec["spectrum"]["counts"] == [5, 5, 0] for rec in spec_stream)


def test_build_output_no_bridge_when_negative(tmp_path):
    # file a: S=[10,0,0], Si_a=[0,0,0]
    a = [_spec(1.0, 1000.0, [10, 0, 0], duration=100.0)]
    # file b: accumulated reset smaller S=[1,0,0] (device restarted -> negative bridge)
    b = [_spec(2.0, 5000.0, [1, 0, 0], duration=0.0)]
    paths = [
        _write(tmp_path, f"raw_{SERIAL}_20260101000000.ndjson", a),
        _write(tmp_path, f"raw_{SERIAL}_20260101010000.ndjson", b),
    ]
    files = [rcmerge._read_file(p) for p in paths]
    out = rcmerge._build_output(SERIAL, files)

    # bridge = clamp([1,0,0]-[10,0,0],0) = [0,0,0]; total = S_a + bridge = [10,0,0]
    assert out[0]["spectrum"]["counts"] == [10, 0, 0]


def test_main(tmp_path, monkeypatch):
    a = _session_a()
    b = _session_b()
    paths = [
        _write(tmp_path, f"raw_{SERIAL}_20260101000000.ndjson", a),
        _write(tmp_path, f"raw_{SERIAL}_20260101010000.ndjson", b),
    ]
    out = str(tmp_path / "merged.ndjson")
    monkeypatch.setattr("sys.argv", [__file__, "-o", out] + paths)
    assert rcmerge.main() is None

    lines = [line for line in open(out) if line.strip()]
    # drop 2 line1s, add line1+line2, plus 1 bridge for the single gap
    assert len(lines) == len(a) + len(b) - 2 + 2 + 1
    mt = [json.loads(line)["monotime"] for line in lines[2:]]
    assert mt == sorted(mt)


def test_iso_to_epoch_edge_cases():
    assert rcmerge._iso_to_epoch("") is None
    assert rcmerge._iso_to_epoch(None) is None
    assert rcmerge._iso_to_epoch("not a timestamp") is None
    assert rcmerge._iso_to_epoch("2026-01-01T00:00:00Z") == 1767225600.0


def test_best_anchor_none():
    records = [{"_type": "RtData", "monotime": 1.0}]  # no GNSS time, no dt
    assert rcmerge._best_anchor(records) is None


def test_read_file_skips_blank_and_garbage(tmp_path):
    p = tmp_path / "junk.ndjson"
    p.write_text(
        '{"_type": "SpecData", "monotime": 1}\n'
        "\n"
        "this is not json\n"
        '{"_type": "RtData", "monotime": 2}\n'
    )
    recs = rcmerge._read_file(str(p))
    assert [r["monotime"] for r in recs] == [1, 2]


def test_first_serial_none():
    assert rcmerge._first_serial([{"_type": "RtData", "monotime": 1}]) is None


def test_validate_no_specdata(tmp_path):
    p = tmp_path / "raw_RC-103-000070_20260101000000.ndjson"
    p.write_text(json.dumps({"_type": "RtData", "monotime": 1}))
    with pytest.raises(ValueError, match="no SpecData"):
        rcmerge._validate([str(p)], [rcmerge._read_file(str(p))])


def test_vec_length_mismatch():
    assert rcmerge._vec_add([1, 2], [3, 4, 5]) == [4, 6, 5]
    assert rcmerge._vec_sub([1, 2, 3], [4, 5]) == [-3, -3]
    assert rcmerge._vec_sub([1, 2], [3, 4, 5]) == [-2, -2]  # trims the longer operand


def test_split_file_leading_nonspec_and_none(tmp_path):
    recs = [
        {"_type": "RtData", "monotime": 1},
        {
            "_type": "SpecData",
            "monotime": 2,
            "serial_number": SERIAL,
            "spectrum": {"duration": 1, "a0": 1, "a1": 2, "a2": 3, "counts": [5, 0, 0]},
        },
        {
            "_type": "SpecData",
            "monotime": 3,
            "serial_number": SERIAL,
            "spectrum": {"duration": 2, "a0": 1, "a1": 2, "a2": 3, "counts": [1, 0, 0]},
        },
    ]
    S, per, Si, last_dur, cal = rcmerge._split_file(recs)
    assert S == [5, 0, 0]
    assert Si == [1, 0, 0]
    assert last_dur == 2.0
    assert cal == (1.0, 2.0, 3.0)
    with pytest.raises(ValueError, match="no SpecData"):
        rcmerge._split_file([{"_type": "RtData", "monotime": 1}])


def test_rebase_anchor_fallback():
    # two sessions, monotime reset, neither has a usable real-time anchor:
    # the rebase falls back to a 1.0s gap
    f1 = [
        {"_type": "SpecData", "monotime": 10.0, "serial_number": SERIAL,
         "spectrum": {"duration": 1, "a0": 1, "a1": 2, "a2": 3, "counts": [5]}},
        {"_type": "RtData", "monotime": 11.0, "serial_number": SERIAL},
    ]
    f2 = [
        {"_type": "SpecData", "monotime": 2.0, "serial_number": SERIAL,
         "spectrum": {"duration": 1, "a0": 1, "a1": 2, "a2": 3, "counts": [0]}},
        {"_type": "RtData", "monotime": 3.0, "serial_number": SERIAL},
    ]
    stream, bridge_dur = rcmerge._rebase([f1, f2], [[0]], SERIAL, (1.0, 2.0, 3.0))
    mt = [rec["monotime"] for rec in stream]
    assert mt == sorted(mt)
    assert bridge_dur == 1.0  # fallback gap
    # the bridge record uses the previous file's last monotime
    assert any(rec.get("_type") == "SpecData" and rec["monotime"] == 11.0 for rec in stream)


def test_build_output_no_records():
    with pytest.raises(ValueError, match="no records"):
        rcmerge._build_output(SERIAL, [[], []])


def test_build_output_gps_first_record():
    gps = {"_type": "GpsData", "monotime": 1.0, "payload": {"time": "2026-01-01T00:00:00Z", "gnss": True, "mode": 3}}
    spec = {"_type": "SpecData", "monotime": 2.0, "serial_number": SERIAL,
            "spectrum": {"duration": 1, "a0": 1, "a1": 2, "a2": 3, "counts": [5]}}
    out = rcmerge._build_output(SERIAL, [[gps, spec]])
    assert out[0]["dt"] == "2026-01-01T00:00:00Z"


def test_build_output_gps_first_no_time(tmp_path):
    gps = {"_type": "GpsData", "monotime": 1.0, "payload": {"time": None, "gnss": True, "mode": 3}}
    spec = {"_type": "SpecData", "monotime": 2.0, "serial_number": SERIAL,
            "spectrum": {"duration": 1, "a0": 1, "a1": 2, "a2": 3, "counts": [5]}}
    out = rcmerge._build_output(SERIAL, [[gps, spec]])
    assert out[0]["dt"] == ""


def test_main_default_output(tmp_path, monkeypatch):
    a = _session_a()
    paths = [_write(tmp_path, f"raw_{SERIAL}_20260101000000.ndjson", a)]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", [__file__] + paths)
    assert rcmerge.main() is None
    assert (tmp_path / f"merged_{SERIAL}.ndjson").exists()

