#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# Author: Chris Kuethe <chris.kuethe@gmail.com> , https://github.com/ckuethe/radiacode-tools
# SPDX-License-Identifier: MIT

import os
from argparse import ArgumentParser, Namespace
from datetime import datetime
from hashlib import sha256 as hf

import pandas as pd

from radiacode_tools.rc_files import RcTrack
from radiacode_tools.rc_types import RangeFinder
from radiacode_tools.rc_utils import localtz
from radiacode_tools.rc_validators import isotime, rcsn


def get_args() -> Namespace:
    "The usual argument parsing stuff"

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
        type=rcsn,
        help="[%(default)s]",
    )
    ap.add_argument(  # -t start-time
        "-t",
        "--start-time",
        default="1984-12-05T00:00:00",
        metavar="TIME",
        type=isotime,
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
    ap.add_argument(  # -P allow-unsanitized-position
        "-P",
        "--allow-unsanitized-position",
        default=False,
        action="store_true",
        help="Preserve original position measurements [%(default)s]",
    )
    ap.add_argument(  # -R reverse-route
        "-R",
        "--reverse-route",
        default=False,
        action="store_true",
        help="Reverse the order of the points, eg. northbound becomes southbound, or clockwise becomes counterclockwise [%(default)s]",
    )
    ap.add_argument(  # -S allow-unsanitized-serial
        "-S",
        "--allow-unsanitized-serial",
        default=False,
        action="store_true",
        help="Preserve original serial number [%(default)s]",
    )
    ap.add_argument(  # -S allow-unsanitized-serial
        "-T",
        "--allow-unsanitized-time",
        default=False,
        action="store_true",
        help="Preserve original timestamps [%(default)s]",
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


def reverse_route(track: RcTrack) -> None:
    # Reverse the order of points while keeping original timestamps
    # This matches the old behavior where timestamps are restored to their original indices
    # after reversing the point list
    timestamps = track.df["DateTime"].tolist()
    new_df = track.df.iloc[::-1].copy()
    new_df["DateTime"] = timestamps
    track._df = new_df
    track._points_cache = None


def sanitize(args: Namespace, track: RcTrack) -> None:
    """
    Iterate over the points in an RcTrack, and mask the selected data

    This generally works by finding the minimum value of a series, subtracting it
    to shift the series to start at 0, then adding a new base offset:
        [5,6,7,8] + -5 -> [0,1,2,3] + 42 -> [42,43,44,45]
    """
    lat_range = RangeFinder("Lat")
    lon_range = RangeFinder("Lon")

    start_dt = track.df.iloc[0]["DateTime"]
    header_text = f"{track.name} {track.serialnumber} {track.comment} {start_dt}"
    header_hash = hf(header_text.encode(), usedforsecurity=False)

    for _, row in track.df.iterrows():
        point_str = f"TrackPoint(dt={row['DateTime']}, latitude={row['Latitude']}, longitude={row['Longitude']}, accuracy={row['Accuracy']}, doserate={row['DoseRate']}, countrate={row['CountRate']})"
        header_hash.update(point_str.encode())
        lat_range.update(row["Latitude"])
        lon_range.update(row["Longitude"])

    if args.allow_unsanitized_comment is False:
        track.comment = args.comment

    if args.allow_unsanitized_serial is False:
        track.serialnumber = args.serial_number

    if args.allow_unsanitized_time:
        args.start_time = start_dt

    if args.allow_unsanitized_name is False:
        track.name = f"{args.prefix}{header_hash.hexdigest()[:32]}"

    if args.allow_unsanitized_position:
        args.base_latitude = lat_range.min_val
        args.base_longitude = lon_range.min_val

    # Create new DataFrame with sanitized values
    new_df = track.df.copy()
    # Convert datetime to timedelta from start, then add new start time
    time_deltas = new_df["DateTime"] - start_dt
    new_df["DateTime"] = args.start_time + time_deltas
    new_df["Latitude"] = new_df["Latitude"] - lat_range.min_val + args.base_latitude
    new_df["Longitude"] = new_df["Longitude"] - lon_range.min_val + args.base_longitude
    new_df["Latitude"] = new_df["Latitude"].round(7)
    new_df["Longitude"] = new_df["Longitude"].round(7)

    if args.reverse_route:
        # Save original times before reversing
        original_times = new_df["DateTime"].tolist()
        new_df = new_df.iloc[::-1].copy()
        # Restore original times to their new positions
        new_df["DateTime"] = original_times

    track._df = new_df
    track._points_cache = None


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
