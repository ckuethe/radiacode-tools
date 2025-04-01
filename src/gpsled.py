#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# Author: Chris Kuethe <chris.kuethe@gmail.com> , https://github.com/ckuethe/radiacode-tools
# SPDX-License-Identifier: MIT

"Drive an LED in response to GPS fix state"

import os
import socket
import subprocess
from argparse import ArgumentParser, Namespace
from json import JSONDecodeError
from json import dumps as jdumps
from json import loads as jloads
from time import sleep

from radiacode_tools.rc_validators import _gpsd

_example_systemd_unit = """
[Unit]
Description=Set a GPIO LED based on gps fix state
Requires=network.target
After=network.target

[Service]
Type=simple
ExecStart=/path/to/gpsled.py -g gpsd://127.0.0.1:2947/ green:lan
Restart=on-failure

[Install]
WantedBy=multi-user.target
"""


def configure_led(args: Namespace, enable: bool = True):
    subprocess.run(["/usr/sbin/modprobe", "ledtrig-pattern"], check=True)
    with open(args.led_path, "w") as ofd:
        print("pattern" if enable else "none", file=ofd)

    if enable is False:
        with open(args.led_path.replace("/trigger", "/brightness"), "w") as ofd:
            print("0", file=ofd)
    else:
        with open(args.led_path.replace("/trigger", "/pattern"), "w") as ofd:
            print("0 495 1 5", file=ofd)


def get_args() -> Namespace:
    def _led(s):
        "check for /trigger because it's available in all modes"
        if isinstance(s, list):
            s = s[0]
        if s == "/dev/null":
            return s
        if s.startswith("/sys/class/leds/") and s.endswith("/trigger"):
            return s
        else:
            return _led(f"/sys/class/leds/{s}/trigger")

    ap = ArgumentParser()
    ap.add_argument(
        "-g",
        "--gpsd",
        type=_gpsd,
        metavar="URL",
        default="gpsd://localhost",
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
        help="/sys/class/leds/<led>/trigger",
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

    watch_args = {"enable": True, "json": True}
    if args.gpsd.get("dev", ""):
        watch_args["device"] = args.gpsd["dev"]
    watchstr = "?WATCH=" + jdumps(watch_args)

    last_state = None
    with open(args.led_path.replace("/trigger", "/pattern"), "wt") as ofd:
        while True:
            try:
                with socket.create_connection(srv, 3) as s:
                    gpsfd = s.makefile("rw")

                    print(watchstr, file=gpsfd, flush=True)
                    dedup = None
                    while True:
                        line = gpsfd.readline().strip()
                        try:
                            x = jloads(line)
                            if x["class"] != "TPV":
                                continue
                            if x["time"] == dedup:
                                continue
                            tpv = {f: x.get(f, None) for f in ["time", "mode", "lat", "lon", "alt", "speed", "track"]}

                            if tpv["mode"] != last_state:
                                if tpv["mode"] == 3:
                                    print("1 100 1 100", flush=True, file=ofd)
                                    tpv["led"] = "on"
                                elif tpv["mode"] == 2:
                                    print("0 250 1 250", flush=True, file=ofd)
                                    tpv["led"] = "blink"
                                else:
                                    print("0 495 1 5", flush=True, file=ofd)
                                    tpv["led"] = "blip"

                            if args.verbose:
                                print(tpv)
                        except (KeyError, JSONDecodeError):  # skip bad messages, no fix, etc.
                            print("0 100", flush=True, file=ofd)
                            break
                    # End of read loop
            except (socket.error, TimeoutError) as e:
                # any other exception will cause this to error out and exit
                if args.verbose:
                    print(f"Reattempting connection after exception: {e}")
                sleep(3)


def main() -> None:
    args = get_args()
    configure_led(args)
    gps_worker(args)


if __name__ == "__main__":
    main()
