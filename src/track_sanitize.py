#!/usr/bin/env python3
import os
import re
from argparse import ArgumentParser, Namespace
from datetime import datetime
from hashlib import sha256 as hf

from rcfiles import RcTrack
from rctypes import RangeFinder


def get_args() -> Namespace:
    "The usual argument parsing stuff"

    def _timestamp(s: str) -> str:
        "helper to enforce time string format"
        m = re.match("^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})Z?$", s.strip())
        if m:
            return datetime(*[int(x) for x in m.groups()])
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
    ap.add_argument(  # -p prefix
        "-p",
        "--prefix",
        type=str,
        default="sanitized_",
        help="[%(default)s]",
    )
    ap.add_argument(  # -s serial-number
        "-s",
        "--serial-number",
        default="RC-100-314159",
        metavar="STR",
        type=_rcsn,
        help="[%(default)s]",
    )
    ap.add_argument(  # -t start-time
        "-t",
        "--start-time",
        default="1984-12-05T00:00:00",
        metavar="TIME",
        type=_timestamp,
        help="[%(default)s]",
    )
    ap.add_argument(  # -x base-longitude
        "-x",
        "--base-longitude",
        default=-55.9269664,
        metavar="LON",
        type=float,
        help="[%(default)f]",
    )
    ap.add_argument(  # -y base-latitude
        "-y",
        "--base-latitude",
        default=43.5833323,
        type=float,
        metavar="LAT",
        help="[%(default)f]",
    )
    ap.add_argument(  # -c comment
        "-c",
        "--comment",
        default='"And I ... was never here."',
        metavar="STR",
        type=str,
        help="[%(default)s]",
    )
    ap.add_argument(  # -C allow-unsanitized-comment
        "-C",
        "--allow-unsanitized-comment",
        default=False,
        action="store_true",
        help="Preserve original comment [%(default)s]",
    )
    ap.add_argument(  # -N allow-unsanitized-name
        "-N",
        "--allow-unsanitized-name",
        default=False,
        action="store_true",
        help="Preserve original track name [%(default)s]",
    )
    ap.add_argument(  # -S allow-unsanitized-serial
        "-S",
        "--allow-unsanitized-serial",
        default=False,
        action="store_true",
        help="Preserve original serial number [%(default)s]",
    )
    ap.add_argument(  # -f force-overwrite
        "-f",
        "--force-overwrite",
        default=False,
        action="store_true",
        help="Overwrite existing files [%(default)s]",
    )
    ap.add_argument(  # -o stdout
        "-o",
        "--stdout",
        default=False,
        action="store_true",
        help="print sanitized track to stdout rather than a file [%(default)s]",
    )
    ap.add_argument(nargs="+", dest="files", metavar="FILE")
    return ap.parse_args()


def sanitize(args: Namespace, track: RcTrack) -> None:
    """
    Iterate over the points in an RcTrack, and mask the selected data
    """
    lat_range = RangeFinder("Lat")
    lon_range = RangeFinder("Lon")

    header_text = f"{track.name} {track.serialnumber} {track.comment} {track.points[0].datetime}"
    header_hash = hf(header_text.encode(), usedforsecurity=False)

    for point in track.points:
        header_hash.update(str(point).encode())
        lat_range.update(point.latitude)
        lon_range.update(point.longitude)

    if args.allow_unsanitized_comment is False:
        track.comment = args.comment

    if args.allow_unsanitized_serial is False:
        track.serialnumber = args.serial_number

    if args.allow_unsanitized_name is False:
        track.name = f"{args.prefix}{header_hash.hexdigest()[:32]}"

    start_timestamp = track.points[0].datetime
    for i, tp in enumerate(track.points):
        track.points[i] = tp._replace(
            datetime=tp.datetime - start_timestamp + args.start_time,
            latitude=round(tp.latitude - lat_range.min_val + args.base_latitude, 7),
            longitude=round(tp.longitude - lon_range.min_val + args.base_latitude, 7),
        )


def main() -> None:
    args = get_args()
    # file deepcode ignore PT: Shut up snyk, this is a CLI utility intended to walk files...
    for filename in args.files:
        track = RcTrack()
        track.load_file(filename)
        sanitize(args, track)
        if args.stdout:
            track.write_file("/dev/stdout")
        else:
            if os.path.exists(filename) and args.force_overwrite is False:
                print(f"Output file {filename} already exists")
                continue
            track.write_file(filename)


if __name__ == "__main__":
    main()
