#!/usr/bin/env python3
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# Author: Chris Kuethe <chris.kuethe@gmail.com> , https://github.com/ckuethe/radiacode-tools
# SPDX-License-Identifier: MIT

"""
rcmerge: merge several rcmultispg ndjson logs into a single continuous recording.

rcmultispg writes one ndjson file per device per recording session. If the USB
cable gets bumped and the device drops off the bus, or the host reboots, the
recording has to be restarted into a fresh file. Each new file restarts the
device's internal spectrum accumulator and, if the host rebooted, restarts the
monotonic clock that rcmultispg uses to order records.

This tool stitches those files back together:

- All inputs must be for a single device (serial number). Files with a serial
  number in the filename that disagrees with the serial number embedded in the
  first spectrum line are rejected, as are inputs from different devices.
- The device's spectrum accumulator almost never resets, so the accumulated
  spectrum is continuous across files. For each inter-file gap a synthetic
  "bridge" spectrum is computed as clamp(S_next - S_this - Si, 0), where S is the
  accumulated spectrum at the start of a file (line 1) and Si is the integrated
  per-sample increments from that file; this accounts for counts accumulated
  while the device was disconnected between files.
- The total accumulated spectrum for the merged recording is the first file's
  accumulated spectrum plus every per-sample increment plus every bridge.
- Records are reordered by monotime. monotime is preserved within a host boot
  (it is immune to host clock jumps); across host reboots, where monotime
  resets, the files are stitched with a real-time gap that is anchored to the
  GNSS time in GpsData records when available (preferring it over the host clock,
  which may not be locked to UTC).

The output is a single ndjson file shaped exactly like one rcmultispg session:

1.  total accumulated spectrum since the merged recording began
2.  an all-zero incremental spectrum
3.  every remaining GpsData, RtData, and per-sample SpecData record, sorted by
    the rebased monotime
"""

import json
import re
from argparse import ArgumentParser, Namespace
from datetime import datetime
from typing import Any

from radiacode_tools.rc_types import RcJSONEncoder

_SERIAL_RE = re.compile(r"(RC-\d{3}[A-Z]?-\d{6})")


def _iso_to_epoch(s: str | None) -> float | None:
    "Parse an ISO-8601 UTC timestamp (with or without a trailing 'Z') into epoch seconds"
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _best_anchor(records: list[dict[str, Any]]) -> tuple[float, float] | None:
    """
    Return a (monotime, real_time_epoch) reference point for a recording session.

    Prefer a GpsData record carrying a valid GNSS navigation solution, since GNSS
    time is absolute UTC and immune to host clock jumps; fall back to the host
    clock (dt) which is what SpecData/RtData carry.
    """
    for rec in records:
        if rec.get("_type") == "GpsData" and rec["payload"].get("mode", 0) >= 2:
            epoch = _iso_to_epoch(rec["payload"].get("time"))
            if epoch is not None:
                return (rec["monotime"], epoch)
    for rec in records:
        epoch = _iso_to_epoch(rec.get("dt"))
        if epoch is not None:
            return (rec["monotime"], epoch)
    return None


def _read_file(path: str) -> list[dict[str, Any]]:
    "Read a single ndjson file into a list of record dicts, skipping blank or corrupt lines"
    records: list[dict[str, Any]] = []
    with open(path) as fd:
        for line in fd:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def _first_serial(records: list[dict[str, Any]]) -> str | None:
    "The serial number of the first SpecData record in a file"
    for rec in records:
        if rec.get("_type") == "SpecData":
            return rec.get("serial_number")
    return None


def _validate(paths: list[str], files: list[list[dict[str, Any]]]) -> str:
    "Enforce single-device merges and reject files whose name/content serial disagrees"
    serials: set[str] = set()
    for path, records in zip(paths, files):
        match = _SERIAL_RE.search(path)
        if match is None:
            raise ValueError(f"{path}: filename has no radiacode serial number")
        serial = _first_serial(records)
        if serial is None:
            raise ValueError(f"{path}: no SpecData records found")
        serials.add(serial)
        if match.group(1) != serial:
            raise ValueError(f"{path}: filename serial {match.group(1)!r} != first spectrum serial {serial!r}")
    if len(serials) > 1:
        raise ValueError(f"cannot merge files from multiple devices: {sorted(serials)}")
    return serials.pop()


def _vec_add(a: list[int], b: list[int]) -> list[int]:
    "Elementwise sum of two count vectors (a is zero-padded to b's length)"
    if len(a) < len(b):
        a = a + [0] * (len(b) - len(a))
    out = list(a)
    for i, x in enumerate(b):
        out[i] += x
    return out


def _vec_sub(a: list[int], b: list[int]) -> list[int]:
    "Elementwise difference a-b of two count vectors"
    if len(b) > len(a):
        b = b[: len(a)]
    return [x - y for x, y in zip(a, b)]


def _vec_clamp_ge0(v: list[int]) -> list[int]:
    "Clamp every element to be >= 0"
    return [max(x, 0) for x in v]


def _sum_counts(records: list[dict[str, Any]]) -> list[int] | None:
    "Elementwise sum of the counts of every SpecData record; None if none found"
    out: list[int] | None = None
    for rec in records:
        if rec.get("_type") != "SpecData":
            continue
        c = rec["spectrum"]["counts"]
        if out is None:
            out = list(c)
        else:
            out = _vec_add(out, c)
    return out


def _split_file(
    records: list[dict[str, Any]],
) -> tuple[list[int], list[dict[str, Any]], list[int], float, tuple[float, float, float]]:
    """
    Split a file into its pieces:
    - line1: the accumulated spectrum (first SpecData record)
    - per_samples: every record that follows it (line2 and later)
    - Si: the integrated per-sample increments (sum of the per-sample SpecData counts)
    - last_dur: the duration of the last per-sample SpecData record (total recording time for this file)
    - cal: the calibration coefficients from line1
    """
    idx = 0
    while idx < len(records) and records[idx].get("_type") != "SpecData":
        idx += 1
    if idx >= len(records):
        raise ValueError("file has no SpecData records")
    line1 = records[idx]
    per_samples = records[idx + 1 :]
    S = line1["spectrum"]["counts"]
    Si = _sum_counts(per_samples) or [0] * len(S)
    last_dur = 0.0
    for rec in reversed(per_samples):
        if rec.get("_type") == "SpecData":
            last_dur = rec["spectrum"].get("duration") or 0.0
            break
    sp = line1["spectrum"]
    cal = (sp.get("a0", 0.0), sp.get("a1", 0.0), sp.get("a2", 0.0))
    return S, per_samples, Si, last_dur, cal


def _make_spec(
    serial: str,
    counts: list[int],
    duration: float,
    monotime: float,
    dt_iso: str,
    cal: tuple[float, float, float],
) -> dict[str, Any]:
    "Build a synthetic SpecData record (used for line1, line2, and bridges)"
    return {
        "dt": dt_iso,
        "monotime": monotime,
        "serial_number": serial,
        "spectrum": {
            "duration": duration,
            "a0": cal[0],
            "a1": cal[1],
            "a2": cal[2],
            "counts": counts,
            "_dataclass": True,
            "_type": "Spectrum",
        },
        "_dataclass": True,
        "_type": "SpecData",
    }


def _compute_bridges(ordered: list[list[dict[str, Any]]]) -> list[list[int] | None]:
    """
    For each gap between consecutive files, bridge = clamp(S_next - S_this - Si_this, 0).
    S is the accumulated spectrum at the start of a file (line1) and Si is the
    integrated per-sample increments from that file, so the bridge accounts for
    counts accumulated on the device while it was disconnected between files.
    """
    metas = [_split_file(f) for f in ordered]
    bridges: list[list[int] | None] = []
    for i in range(len(ordered) - 1):
        S_i, _, Si_i, _, _ = metas[i]
        S_next, _, _, _, _ = metas[i + 1]
        bridge = _vec_sub(S_next, _vec_add(S_i, Si_i))
        bridges.append(_vec_clamp_ge0(bridge))
    return bridges


def _rebase(ordered, bridges, serial, cal):
    """
    Stitch per-file records into one monotone stream.

    Each file's records are already sorted by monotime. monotime is the ordering
    source of truth within a host boot. When a file opens with a monotime smaller
    than the previous file's last monotime, the host rebooted and monotime reset;
    the sessions are joined with a real-time gap anchored to the GNSS (or host
    clock) reference points of each session. The first session keeps its monotime
    unchanged.

    A synthetic "bridge" spectrum is inserted at each inter-file gap, accounting
    for the elapsed time (and any counts accumulated while disconnected) between
    the last measurement of one file and the first measurement of the next.
    Returns the stream and the total elapsed time covered by the bridges.
    """
    stream: list[dict[str, Any]] = []
    total_bridge_dur: float = 0.0
    prev_last_mt: float | None = None
    prev_last_global: float | None = None
    prev_anchor: tuple[float, float] | None = None
    prev_first_dt_iso: str = ""
    offset: float = 0.0
    first_file = True

    for idx, records in enumerate(ordered):
        first_mt = records[0]["monotime"]
        last_mt = records[-1]["monotime"]
        anchor = _best_anchor(records)
        first_dt_iso = records[0].get("dt") or (
            records[0]["payload"].get("time") if records[0]["_type"] == "GpsData" else ""
        )
        if not first_dt_iso:
            first_dt_iso = ""

        if not first_file and prev_last_mt is not None and first_mt < prev_last_mt:  # host reboot
            assert prev_last_global is not None  # guaranteed by the previous iteration
            cur_first_real = None
            prev_last_real = None
            if anchor is not None:
                cur_first_real = anchor[1] + (first_mt - anchor[0])
            if prev_anchor is not None:
                prev_last_real = prev_anchor[1] + (prev_last_mt - prev_anchor[0])
            if cur_first_real is not None and prev_last_real is not None:
                gap = max(cur_first_real - prev_last_real, 0.0)
            else:
                gap = 1.0
            offset = prev_last_global + gap - first_mt
        elif first_file:
            offset = 0.0
            first_file = False

        # insert the bridge for the gap just before this file's records
        if idx > 0 and prev_last_global is not None:
            bridge_counts = bridges[idx - 1] or [0] * len(bridges[idx - 1] or [0])
            gap_dur = (first_mt + offset) - prev_last_global
            stream.append(_make_spec(serial, bridge_counts, gap_dur, prev_last_global, prev_first_dt_iso, cal))
            total_bridge_dur += max(gap_dur, 0.0)

        for rec in records[1:]:  # everything after the accumulated snapshot
            newrec = dict(rec)
            newrec["monotime"] = rec["monotime"] + offset
            stream.append(newrec)

        prev_last_mt = last_mt
        prev_last_global = last_mt + offset
        prev_anchor = anchor
        prev_first_dt_iso = first_dt_iso

    return stream, total_bridge_dur


def _build_output(serial: str, files: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    "Build the merged ndjson record list for a single device"
    files = [f for f in files if f]
    if not files:
        raise ValueError("no records to merge")

    # order files chronologically by their GNSS/host real-time anchor
    def _order_key(records):
        anchor = _best_anchor(records)
        return (anchor[1] if anchor else 0.0, _first_serial(records) or "")

    ordered = sorted(files, key=_order_key)

    for records in ordered:
        records.sort(key=lambda r: r["monotime"])

    metas = [_split_file(f) for f in ordered]
    bridges = _compute_bridges(ordered)

    # total accumulated spectrum = first file's accumulated snapshot + every
    # per-sample increment + every gap bridge
    total_counts: list[int] = list(metas[0][0])  # S of the first file
    for i in range(len(ordered)):
        total_counts = _vec_add(total_counts, metas[i][2])  # + Si_i
    for b in bridges:
        if b is not None:
            total_counts = _vec_add(total_counts, b)  # + bridge

    cal = metas[0][4]
    nch = len(total_counts)

    stream, total_bridge_dur = _rebase(ordered, bridges, serial, cal)
    stream.sort(key=lambda r: r["monotime"])

    # total duration = first file's accumulated duration + each file's recording
    # time (last per-sample duration) + all bridge gap durations
    first_line1_dur = ordered[0][0].get("spectrum", {}).get("duration") or 0.0
    total_duration = first_line1_dur + sum(m[3] for m in metas) + total_bridge_dur

    first_rec = ordered[0][0]
    if first_rec["_type"] == "GpsData":
        first_dt_iso = first_rec["payload"].get("time")
    else:
        first_dt_iso = first_rec.get("dt")
    if not first_dt_iso:
        first_dt_iso = ""

    line1 = _make_spec(serial, total_counts, total_duration, 0.0, first_dt_iso, cal)
    line2 = _make_spec(serial, [0] * nch, 0.0, 0.0, first_dt_iso, cal)
    return [line1, line2] + stream


def get_args() -> Namespace:
    "The usual argparse stuff"
    ap = ArgumentParser(description="Merge several rcmultispg ndjson logs into a single continuous recording")
    ap.add_argument("files", nargs="+", metavar="FILE", help="rcmultispg ndjson log files to merge")
    ap.add_argument(
        "-o",
        "--output",
        type=str,
        metavar="FILENAME",
        help="merged output filename [merged_<serial>.ndjson]",
    )
    ap.add_argument(
        "-p",
        "--prefix",
        type=str,
        metavar="STR",
        default="merged_",
        help="prefix for generated filename [%(default)s]",
    )
    return ap.parse_args()


def main() -> None:
    args = get_args()
    files = [_read_file(path) for path in args.files]
    serial = _validate(args.files, files)
    records = _build_output(serial, files)

    if args.output:
        outname = args.output
    else:
        outname = f"{args.prefix}{serial}.ndjson"

    enc = RcJSONEncoder()
    with open(outname, "w") as ofd:
        for rec in records:
            print(enc.encode(rec), file=ofd, flush=True)


if __name__ == "__main__":
    main()
