#!/usr/bin/env python3
import datetime
import os
import re
from argparse import ArgumentParser, Namespace
from collections import namedtuple
from hashlib import sha256 as hf
from tempfile import mkstemp
from typing import List

from rcutils import DateTime2FileTime

_trackpoint_fields = ["timestamp", "time", "latitude", "longitude", "accuracy", "doserate", "countrate", "comment"]
TrackPoint = namedtuple("TrackPoint", field_names=_trackpoint_fields, defaults=[None] * len(_trackpoint_fields))


class RangeFinder:
    "A helper class to determine the range of a list"

    def __init__(self, name: str = "RangeFinder"):
        self.name = name
        self.min_val = None
        self.max_val = None

    def update(self, x):
        self.min_val = x if self.min_val is None else min(x, self.min_val)
        self.max_val = x if self.max_val is None else max(x, self.max_val)

    def get(self):
        return (self.min_val, self.max_val)

    def __str__(self):
        return f"{self.name}(min={self.min_val}, max={self.max_val})"

    def __repr__(self):
        print(self.__str__())


def get_args() -> Namespace:
    "The usual argument parsing stuff"

    def _timestamp(s: str) -> str:
        "helper to enforce time string format"
        m = re.match("^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})Z?$", s.strip())
        if m:
            return datetime.datetime(*[int(x) for x in m.groups()])
        else:
            raise ValueError("Invalid time format")

    def _rcsn(s: str) -> str:
        "helper to check the format of a radiacode serial number"
        if re.match("RC-\d{3}[G]?-\d{6}", s.strip()):
            return s
        return ""

    ap = ArgumentParser(
        description="Sanitize a Radiacode track by rebasing it (to the notional setting of Hunt for Red October)"
    )
    ap.add_argument(
        "-p",
        "--prefix",
        type=str,
        default="sanitized_",
        help="[%(default)s]",
    )
    ap.add_argument(
        "-s",
        "--serial-number",
        default="RC-100-314159",
        metavar="STR",
        type=_rcsn,
        help="[%(default)s]",
    )
    ap.add_argument(
        "-t",
        "--start-time",
        default="1984-12-05T00:00:00",
        metavar="TIME",
        type=_timestamp,
        help="[%(default)s]",
    )
    ap.add_argument(
        "-x",
        "--base-longitude",
        default=-55.9269664,
        metavar="LON",
        type=float,
        help="[%(default)f]",
    )
    ap.add_argument(
        "-y",
        "--base-latitude",
        default=43.5833323,
        type=float,
        metavar="LAT",
        help="[%(default)f]",
    )
    ap.add_argument(
        "-c",
        "--comment",
        default="And I ... was never here.",
        metavar="STR",
        type=str,
        help="[%(default)s]",
    )
    ap.add_argument(
        "-C",
        "--allow-unsanitized-comment",
        default=False,
        action="store_true",
        help="Preserve original comment [%(default)s]",
    )
    ap.add_argument(
        "-I",
        "--force-input",
        default=False,
        action="store_true",
        help="Allow processing of files that begin with the chosen prefix [%(default)s]",
    )
    ap.add_argument(
        "-N",
        "--allow-unsanitized-name",
        default=False,
        action="store_true",
        help="Preserve original track name [%(default)s]",
    )
    ap.add_argument(
        "-O",
        "--force-overwrite",
        default=False,
        action="store_true",
        help="Overwrite existing files [%(default)s]",
    )
    ap.add_argument(
        "-d",
        "--dry-run",
        default=False,
        action="store_true",
        help="Do not emit any output files [%(default)s]",
    )
    ap.add_argument(nargs="+", dest="files", metavar="FILE")
    return ap.parse_args()


def parse_row(args: Namespace, s: str) -> TrackPoint:
    "Parse a single point into more specific points"
    tmp = s.strip("\n").split("\t")
    tmp[0] = int(tmp[0])
    tmp[1] = datetime.datetime.strptime(tmp[1], "%Y-%m-%d %H:%M:%S")
    for i in range(2, 7):  # latitude .. countrate
        tmp[i] = float(tmp[i])
    return TrackPoint(*tmp)


def sanitize(args: Namespace, lines: List[str]) -> None:
    """
    Given a list of input lines, return a list of their sanitized versions.
    """
    header = None
    columns: List[str] = None
    start_timestamp = None
    lat_range = RangeFinder("Lat")
    lon_range = RangeFinder("Lon")
    header_hash = hf(b"", usedforsecurity=False)
    for i, line in enumerate(lines):
        header_hash.update(line.encode())
        if line.startswith("Track: "):
            header = line.strip().split("\t")
            header[1] = args.serial_number
            if args.allow_unsanitized_comment is False:
                header[2] = args.comment
        elif line.startswith("Timestamp\t"):
            columns = line.strip("\n")
        else:
            lines[i] = parse_row(args, line)
            lat_range.update(lines[i].latitude)
            lon_range.update(lines[i].longitude)

    if args.allow_unsanitized_name is False:
        header[0] = f"Track: {args.prefix}{header_hash.hexdigest()[:32]}"
    rv: List[str] = []
    rv.append("\t".join(header))
    rv.append(columns)
    start_timestamp = lines[2].time
    for r in lines[2:]:
        row_dict = r._asdict()
        t = args.start_time + (row_dict["time"] - start_timestamp)
        row_dict["time"] = t.strftime("%Y-%m-%d %H:%M:%S")
        row_dict["timestamp"] = DateTime2FileTime(t)
        row_dict["latitude"] = f'{row_dict["latitude"] - lat_range.min_val + args.base_latitude:0.7f}'
        row_dict["longitude"] = f'{row_dict["longitude"] - lon_range.min_val + args.base_longitude:0.7f}'
        r = TrackPoint(*row_dict.values())
        rs = "\t".join([str(v) for v in r._asdict().values()])
        rv.append(rs)
    return rv


def save_file(args: Namespace, cur_fn: str, lines: List[str]) -> None:
    file_name = os.path.basename(cur_fn)
    dir_name = os.path.dirname(cur_fn)
    dest_filename = os.path.join(dir_name, f"{args.prefix}{file_name}")
    if args.dry_run:
        print(f"Not writing to {dest_filename}")
        print("\n".join(lines))
        return
    if os.path.exists(dest_filename) and args.force_overwrite is False:
        raise FileExistsError

    tmp_fd, tmp_fn = mkstemp(dir=dir_name)
    os.close(tmp_fd)
    with open(tmp_fn, "at") as ofd:
        ofd.write("\n".join(lines))
    os.rename(tmp_fn, dest_filename)


def main() -> None:
    args = get_args()
    for filename in args.files:
        if os.path.basename(filename).startswith(args.prefix) and args.force_input is False:
            continue

        with open(filename) as ifd:
            lines = ifd.readlines()
            lines = sanitize(args, lines)
            save_file(args, filename, lines)


if __name__ == "__main__":
    main()
