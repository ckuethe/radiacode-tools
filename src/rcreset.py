#!/usr/bin/env python3
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# Author: Chris Kuethe <chris.kuethe@gmail.com> , https://github.com/ckuethe/radiacode-tools
# SPDX-License-Identifier: MIT

"""
Reset the accumulated spectrum, accumulated dose, and/or the data buffer on one
or more RadiaCode PSRDs.

By default the detector is powered on before any operation and powered off again
when the operation is complete. Use the --keep-* flags to preserve the spectrum,
dose, or data buffer contents. Use --dry-run to see what would happen without
actually touching any device.
"""

import sys
from argparse import ArgumentParser, Namespace
from threading import Thread
from time import sleep
from typing import Any

import usb.core  # type: ignore
from radiacode import RadiaCode  # type: ignore
from radiacode.transports.usb import DeviceNotFound  # type: ignore

from radiacode_tools.rc_types import RcHwInfo
from radiacode_tools.rc_utils import find_radiacode_devices, get_device_id
from radiacode_tools.rc_validators import rcsn


def get_args() -> Namespace:
    "The usual argparse stuff"

    ap = ArgumentParser(description="Reset dose, spectrum, and data buffer on RadiaCode PSRDs")
    ap.add_argument(
        "-d",
        "--dev",
        type=rcsn,
        dest="devs",
        metavar="SERIAL",
        default=[],
        action="append",
        help="Serial number of target device. May be repeated for multiple devices.",
    )
    ap.add_argument(
        "-a",
        "--all",
        default=False,
        action="store_true",
        help="operate on all connected devices",
    )
    ap.add_argument(
        "--keep-spectrum",
        default=False,
        action="store_true",
        help="do not reset the accumulated spectrum",
    )
    ap.add_argument(
        "--keep-dose",
        default=False,
        action="store_true",
        help="do not reset the accumulated dose",
    )
    ap.add_argument(
        "--keep-databuf",
        default=False,
        action="store_true",
        help="do not read (and thus discard) the data buffer",
    )
    ap.add_argument(
        "--dry-run",
        default=False,
        action="store_true",
        help="print what would happen without touching any device",
    )
    ap.add_argument(
        "--no-poweroff",
        default=False,
        action="store_true",
        help="leave the detector powered on when the operation is complete",
    )
    rv: Namespace = ap.parse_args()

    if not rv.all and not rv.devs:
        ap.error("no devices specified; use --dev SERIAL or --all")

    return rv


def reset_device(args: Namespace, serial_number: str) -> None:
    """Connect to a single device and perform the requested resets."""
    if args.dry_run:
        print(f"{serial_number}: dry run - no device operations performed")
        return

    try:
        rc: RadiaCode = RadiaCode(serial_number=serial_number)
    except (usb.core.USBTimeoutError, usb.core.USBError, DeviceNotFound) as e:
        print(f"{serial_number}: failed to connect: {e}", file=sys.stderr)
        return

    try:
        dev_id: RcHwInfo = get_device_id(rc)
        print(f"{serial_number}: connected ({dev_id.product} {dev_id.model})")

        # turn the detector on before doing anything
        rc.set_device_on(True)
        print(f"{serial_number}: powered on")

        if not args.keep_spectrum:
            rc.spectrum_reset()
            print(f"{serial_number}: spectrum reset")
        else:
            print(f"{serial_number}: spectrum kept")

        if not args.keep_dose:
            rc.dose_reset()
            print(f"{serial_number}: dose reset")
        else:
            print(f"{serial_number}: dose kept")

        if not args.keep_databuf:
            # reading the data buffer drains it; the events are discarded.
            # there can be lots of items queued up, so poll repeatedly until
            # no more come back, waiting a bit between polls.
            total_events = 0
            while True:
                events: list[Any] = rc.data_buf()
                total_events += len(events)
                if not events:
                    break
                sleep(0.1)
            print(f"{serial_number}: data buffer read and discarded ({total_events} events)")
        else:
            print(f"{serial_number}: data buffer kept")

        if not args.no_poweroff:
            rc.set_device_on(False)
            print(f"{serial_number}: powered off")
        else:
            print(f"{serial_number}: left powered on")
    finally:
        rc.close()


def main() -> None:
    args: Namespace = get_args()

    if args.all:
        try:
            dev_names: list[str] = find_radiacode_devices()
        except (usb.core.USBError, DeviceNotFound) as e:
            print(f"failed to enumerate devices: {e}", file=sys.stderr)
            sys.exit(1)
        if not dev_names:
            print("no devices found", file=sys.stderr)
            sys.exit(1)
        args.devs = dev_names
    else:
        # only operate on devices that are actually present
        try:
            present: list[str] = find_radiacode_devices()
        except (usb.core.USBError, DeviceNotFound):
            present = []
        missing: set[str] = set(args.devs).difference(set(present))
        if missing:
            print(f"skipping missing devices: {' '.join(sorted(missing))}", file=sys.stderr)
        args.devs = list(set(args.devs).intersection(set(present)))
        if not args.devs:
            print("no requested devices are connected", file=sys.stderr)
            sys.exit(1)

    # reset all devices in parallel, one thread per device
    threads: list[Thread] = [
        Thread(target=reset_device, args=(args, serial_number), name=f"reset-{serial_number}")
        for serial_number in args.devs
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


if __name__ == "__main__":
    main()
