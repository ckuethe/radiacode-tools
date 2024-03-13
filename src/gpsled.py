#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

"Drive an LED in response to GPS fix state"

from argparse import ArgumentParser, Namespace
from re import match as re_match
from time import sleep
import socket
from json import loads as jloads, JSONDecodeError
import os


def get_args() -> Namespace:
    def _gpsd(s):
        m = re_match(r"^gpsd://(?P<host>[a-zA-Z0-9_.-]+)(:(?P<port>\d+))?(?P<dev>/.+)?", s)
        if m:
            return m.groupdict()
        else:
            return None

    def _led(s):
        if isinstance(s, list):
            s = s[0]
        if s == "/dev/null":
            return s
        if s.startswith("/sys/class/leds/") and s.endswith("/brightness"):
            return s
        else:
            return _led(f"/sys/class/leds/{s}/brightness")

    ap = ArgumentParser(description="Poll all connected RadiaCode PSRDs and produce spectrograms")
    ap.add_argument(
        "-g",
        "--gpsd",
        type=_gpsd,
        metavar="URL",
        help="Connect to specified device, eg. gpsd://localhost:2947/dev/ttyACM0",
    )
    ap.add_argument(
        "-v",
        "--verbose",
        default=False,
        action="store_true",
    )
    ap.add_argument(
        nargs=1,
        dest="led_path",
        metavar="PATH",
        type=_led,
        help="/sys/class/leds/<led>/brightness",
    )

    args = ap.parse_args()
    args.led_path = args.led_path[0]

    if args.gpsd is None:
        args.gpsd = {"host": "localhost", "port": "2947", "dev": ""}
    return args


def gps_worker(args: Namespace) -> None:
    "Feed position fixes from a GPSD instance into the logs"
    srv = (args.gpsd["host"], 2947 if args.gpsd["port"] is None else args.gpsd["port"])

    if not os.path.exists(args.led_path):
        raise FileNotFoundError(args.led_path)

    with open(args.led_path, "at") as ofd:
        while True:
            try:
                with socket.create_connection(srv, 3) as s:
                    gpsfd = s.makefile("rw")

                    print('?WATCH={"enable":true,"json":true}', file=gpsfd, flush=True)
                    dedup = None
                    led_state = False
                    while True:
                        line = gpsfd.readline().strip()
                        try:
                            x = jloads(line)
                            if x["class"] != "TPV":
                                continue
                            if x["time"] == dedup:
                                continue
                            tpv = {f: x.get(f, None) for f in ["time", "mode", "lat", "lon", "alt", "speed", "track"]}
                            if tpv["mode"] == 3:
                                led_state = True
                            elif tpv["mode"] == 2:
                                led_state = not led_state
                            else:
                                led_state = False

                            tpv["led_state"] = led_state
                            if args.verbose:
                                print(tpv)
                            print("1" if led_state else "0", flush=True, file=ofd)
                        except (KeyError, JSONDecodeError):  # skip bad messages, no fix, etc.
                            print("0", flush=True, file=ofd)
                            break
                    # End of read loop
            except KeyboardInterrupt:
                print("0", flush=True, file=ofd)
                return
            except (socket.error, TimeoutError) as e:
                if args.verbose:
                    print(f"Reattempting connection after exception: {e}")
                sleep(3)


def main() -> None:
    args = get_args()
    gps_worker(args)


if __name__ == "__main__":
    main()
