#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# Author: Chris Kuethe <chris.kuethe@gmail.com> , https://github.com/ckuethe/radiacode-tools
# SPDX-License-Identifier: MIT

import datetime
import json
import logging
import os
import tempfile
import time
from argparse import ArgumentParser, Namespace
from sys import stderr
from typing import Any

import radiacode
import radiacode.types
from usb import USBError

from radiacode_tools.rc_types import RcJSONEncoder


def get_args() -> Namespace:
    ap = ArgumentParser(
        description="Download and stream the contents of the device Data Buffer",
        epilog="CAUTION: downloading will clear the data buffer, meaning that the "
        "data will no longer be available to any other client such as the official "
        "radiacode apps.",
    )
    mx = ap.add_mutually_exclusive_group()
    mx.add_argument(
        "-d",
        "--device",
        metavar="STR",
        type=str,
        default=None,
        help="Connect to device identified by USB serial-number",
    )
    mx.add_argument(
        "-b",
        "--btaddr",
        metavar="STR",
        type=str,
        default=None,
        help="Connect to device identified by BlueTooth MAC",
    )
    ap.add_argument(
        "-j",
        "--jsonlog",
        default=False,
        action="store_true",
        help="Store downloaded data in a json file [%(default)s]",
    )
    ap.add_argument(
        "-s",
        "--stdout",
        default=False,
        action="store_true",
        help="Also print results to stdout when logging to a json file [%(default)s]",
    )
    ap.add_argument(
        "-r",
        "--no-rtdata",
        default=False,
        action="store_true",
        help="Don't display RealTimeData [%(default)s]",
    )
    ap.add_argument(
        "-x",
        "--raise-exceptions",
        default=False,
        action="store_true",
        help="Don't suppress low level decoder errors, for developers [%(default)s]",
    )
    return ap.parse_args()


def main() -> None:
    args = get_args()
    logging.basicConfig(level=logging.DEBUG)
    print(f"Using {radiacode}", file=stderr)

    if args.btaddr:
        rc = radiacode.RadiaCode(bluetooth_mac=args.btaddr)
    else:
        rc = radiacode.RadiaCode(serial_number=args.device)

    # make sure I didn't break these
    dev_id = rc.serial_number()
    print(f"Connected to {dev_id}", file=stderr)
    print(f"HW Serial Number {rc.hw_serial_number()}")
    print(f"FW Signature {rc.fw_signature()}")
    print(f"FW Version {rc.fw_version()}")

    # if you don't turn the device on, you don't get any spectrum data.
    # If you try poll you just get all zeroes.
    rc.set_device_on(True)

    # Figure out a good way to poll the radiacode to see if it's actually
    # turned on
    assert sum(rc.spectrum_accum().counts)
    # assert len(rc.commands()) > 1024
    # assert len(rc.configuration()) > 1024

    fn = "/dev/stdout"
    copy_to_stdout = False
    if args.jsonlog:
        tfd, tfn = tempfile.mkstemp(dir=".")
        os.close(tfd)
        fn = datetime.datetime.now().strftime(f"rtlog_{dev_id}_%Y%m%d%H%M%S.ndjson")
        os.rename(tfn, fn)
        print(f"Logging to {fn}", file=stderr)
        copy_to_stdout = args.stdout

    with open(fn, "w") as ofd:
        while True:
            now = datetime.datetime.now().replace(microsecond=0)

            try:
                for msg in rc.data_buf():
                    if args.no_rtdata and isinstance(msg, radiacode.types.RealTimeData):
                        continue

                    decoded: dict[str, Any] = {
                        "host_time": now,
                        "message_time": None,
                        "serial": dev_id,
                        "type": msg.__class__.__name__,
                    }

                    # messages are dataclasses which have a __dict__ property that makes
                    # them look like a dict() which can be merged into `decoded`
                    decoded.update(msg.__dict__)

                    # I hate the name "dt", so change it so something more descriptive
                    decoded["message_time"] = decoded.pop("dt", None)

                    # Don't need all the very insignificant digits
                    if "count_rate" in decoded:
                        decoded["count_rate"] = round(decoded["count_rate"], 3)
                    if "dose_rate" in decoded:
                        decoded["dose_rate"] = float(f"{decoded['dose_rate']:.4g}")

                    # flags are more easier to read/decode in hex rather than decimal
                    # eventually I will figure out what the flags actually mean.
                    if "flags" in decoded:
                        decoded["flags"] = f"{decoded['flags']:04x}"
                    if "real_time_flags" in decoded:
                        decoded["real_time_flags"] = f"{decoded['real_time_flags']:04x}"

                    if isinstance(msg, radiacode.types.Event) and msg.event == radiacode.types.EventId.TEXT_MESSAGE:
                        decoded["text"] = rc.text_message().strip()
                    jdata = json.dumps(decoded, cls=RcJSONEncoder)
                    print(jdata, file=ofd, flush=True)
                    if copy_to_stdout:
                        print(jdata, flush=True)
            except (KeyboardInterrupt, USBError, IOError):
                break
            except ValueError as e:
                # something else went wrong, but let's try continue
                if args.raise_exceptions:
                    raise
                else:
                    print(f"Ignoring Radiacode exception {e}")

            time.sleep(0.5)
    return


if __name__ == "__main__":
    main()
