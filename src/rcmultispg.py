#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

"A tool for grabbing spectra from multiple radiacode devices at the same time"

import usb.core
from argparse import ArgumentParser, Namespace
from radiacode import RadiaCode, Spectrum
from radiacode.transports.usb import DeviceNotFound
from threading import Barrier, BrokenBarrierError, Thread, Lock
from time import sleep, time, strftime, gmtime
from binascii import hexlify
from collections import namedtuple
from struct import pack as struct_pack
from re import sub as re_sub
from typing import List, Union
from datetime import datetime
from json import dump as jdump
from signal import signal, SIGUSR1
import sys

Number = Union[int, float]
SpecData = namedtuple("SpecData", ["time", "spectrum"])

RUNNING: bool = True  # Signal when it's time for the threads to exit
USR1FLAG: bool = False  # Signal when SIGUSR1 is caught, to trigger a snapshot
STDIO_LOCK: Lock = Lock()  # Prevent stdio corruption
THREAD_BARRIER: Barrier = Barrier(0)  # intialized to 0 to shut up static type checking


def tbar(wait_time=None) -> None:
    """
    Helper to synchronize all threads; when the last one arrives it resets the barrier.

    Optionally accepts a timeout value; if this time elapsed without the barrier being
    reached by the required threads, a BarrierException is raised.
    """
    if 0 == THREAD_BARRIER.wait(wait_time):
        THREAD_BARRIER.reset()


def handle_sigusr1(_signum=None, _stackframe=None):
    """Set a flag when SIGUSR1 is received, to trigger a state dump"""
    global USR1FLAG
    USR1FLAG = True


# The spectrogram format uses FileTime, the number of 100ns intervals since the
# beginning of 1600 CE. On a linux/unix/bsd host, we get the number of (fractional)
# seconds since the beginning of 1970 CE. Here are some conversions, which, If I use
# them one more time are getting moved into a utility file...

jiffy = 1e-7
epoch_offset_jiffies = 116444736000000000


def FileTime2UnixTime(x: Number) -> float:
    return (float(x) - epoch_offset_jiffies) * jiffy


def FileTime2DateTime(x: Number) -> datetime:
    return datetime.fromtimestamp(FileTime2UnixTime(x))


def UnixTime2FileTime(x: Number) -> int:
    return int(float(x) / jiffy + epoch_offset_jiffies)


def DateTime2FileTime(dt: datetime) -> int:
    return UnixTime2FileTime(dt.timestamp())


def find_radiacode_devices() -> List[str]:
    "List all the radiacode devices detected"
    return [  # No error handling. Caller can deal with any errors.
        d.serial_number
        for d in usb.core.find(idVendor=0x0483, idProduct=0xF123, find_all=True)
        if d.serial_number.startswith("RC-")
    ]


def get_args() -> Namespace:
    "The usual argparse stuff"

    def gte_zero(s):
        f = float(s)
        if f < 0.0:
            raise ValueError("value cannot be less than 0")
        return f

    ap = ArgumentParser(description="Poll all connected RadiaCode PSRDs and produce spectrograms")
    ap.add_argument(
        "-d",
        "--dev",
        type=str,
        dest="devs",
        metavar="STR",
        default=[],
        action="append",
        help="USB ID of target device. May be repeated for multiple devices. Leave blank to use all connected devices",
    )
    ap.add_argument(
        "-a",
        "--require-all",
        default=False,
        action="store_true",
        help="abort if not all specified devices can be attached",
    )
    ap.add_argument(
        "-i",
        "--interval",
        type=gte_zero,
        metavar="FLOAT",
        default=5.0,
        help="Polling interval in seconds [%(default).1fs]",
    )
    ap.add_argument(
        "-p",
        "--prefix",
        default="rcmulti_",
        metavar="STR",
        type=str,
        help="prefix for generated filename [%(default)s]",
    )
    ap.add_argument(
        "--reset-dose",
        default=False,
        action="store_true",
        help="reset the internal dose meter",
    )
    ap.add_argument(
        "--reset-spectrum",
        default=False,
        action="store_true",
        help="reset the currently displayed spectrum",
    )
    ap.add_argument(
        "--save-raw-data",
        dest="pickle",
        default=False,
        action="store_true",
        help="Dump raw measurements to a json file",
    )

    rv = ap.parse_args()
    if rv.interval < 0.2:
        print("increasing poll interval to 0.2")
        rv.interval = 0.2

    # post-processing stages.
    rv.devs = list(set(rv.devs))
    return rv


def make_spectrogram_header(
    duration: int,
    serial_number: str,
    start_time: Number,
    name: str = "",
    comment: str = "",
    flags: int = 1,
    channels: int = 1024,
) -> str:
    """
    Create the first (header) line of the spectrum file

    Not all flag values are known, but bit 0 being unset means that the
    spectrogram recording was interrupted and resumed.
    """

    start_time = float(start_time)  # accept reasonable inputs: 1700000000, 1.7e9, "1.7e9", ...
    file_time = UnixTime2FileTime(start_time)
    gt = gmtime(start_time)
    tstr = strftime("%Y-%m-%d %H:%M:%S", gt)  # This one is for the header

    if not name:
        # and this version of time just looks like an int... for deduplication
        name = f"rcmulti-{strftime('%Y%m%d%H%M%S', gt)}-{serial_number}"

    fields = [
        f"Spectrogram: {name.strip()}",
        f"Time: {tstr}",
        f"Timestamp: {file_time}",
        f"Accumulation time: {int(duration)}",
        f"Channels: {channels}",
        f"Device serial: {serial_number.strip()}",
        f"Flags: {flags}",
        f"Comment: {comment}",
    ]
    return "\t".join(fields)


def make_spectrum_line(x: Spectrum) -> str:
    """
    Encode a spectrum (probably the lifetime accumulated dose) for the second line of the file
    (duration:int, coeffs:float[3], counts:int[1024])
    """
    v = struct_pack("<Ifff1024I", int(x.duration.total_seconds()), x.a0, x.a1, x.a2, *x.counts)
    v = hexlify(v, sep=" ").decode()
    return f"Spectrum: {v}"


def format_spectra(data: List[SpecData]) -> str:
    """
    Given the list of SpecData, convert them to whatever we need for the spectrogram

    data[0] = all-time accumulated spectrum - survives "reset accumulation"
    data[1] = current accumulated spectrum at the start of measurement. needed to compute
    data[2:] = the rest of the spectra
    """
    lines = []
    prev_rec = data[1]
    for rec in data[2:]:
        ts = rec.time
        line = [UnixTime2FileTime(ts), int(ts - prev_rec.time)]
        line.extend([int(x[0] - x[1]) for x in zip(rec.spectrum.counts, prev_rec.spectrum.counts)])
        prev_rec = rec
        line = "\t".join([str(x) for x in line])
        line = re_sub(r"(\s0)+$", "", line)
        lines.append(line)

    return "\n".join(lines)


def save_data(
    data: List[SpecData],
    serial_number: str,
    prefix: str = "rcmulti_",
    use_pickle: bool = False,
):
    duration = data[-1].time - data[2].time
    start_time = data[0].time
    time_string = strftime("%Y%m%d%H%M%S", gmtime(start_time))
    fn = f"{prefix}{serial_number}_{time_string}"

    header = make_spectrogram_header(
        duration=duration,
        serial_number=serial_number,
        start_time=start_time,
    )

    def make_rec(data: SpecData):
        rec = {
            "capture_timestamp": data.time,
            "duration": data.spectrum.duration.total_seconds(),
            "calibration": [data.spectrum.a0, data.spectrum.a1, data.spectrum.a2],
            "counts": data.spectrum.counts,
        }
        return rec

    if use_pickle:
        # pickle bad, json, csv?
        with open(f"{fn}.json", "w") as ofd:
            jdump([make_rec(d) for d in data], ofd, indent=2)

    with open(f"{fn}.rcspg", "w") as ofd:
        print(header, file=ofd)
        print(make_spectrum_line(data[-1].spectrum), file=ofd)
        print(format_spectra(data), file=ofd)


def rc_worker(args: Namespace, serial_number: str, start_time: Number) -> None:
    """
    Thread responsible for data acquisition. Connects to devices, polls spectra,
    accumulates data, and generates the output file
    """

    global RUNNING, USR1FLAG
    try:
        rc = RadiaCode(serial_number=serial_number)
    except (usb.core.USBTimeoutError, usb.core.USBError, DeviceNotFound) as e:
        with STDIO_LOCK:
            print(f"{serial_number} failed to connect - cable error, device disconnect? {e}")
        RUNNING = False
        return

    with STDIO_LOCK:
        print(f"{serial_number} Connected ")
    data: List[SpecData] = [SpecData(time(), rc.spectrum_accum())]

    # wait for all threads to connect to their devices
    if THREAD_BARRIER.n_waiting >= 1:
        with STDIO_LOCK:
            print(f"{serial_number} waiting for device connections")

    try:
        tbar(3)
    except BrokenBarrierError:
        return

    if args.reset_spectrum:
        rc.spectrum_reset()
    if args.reset_dose:
        rc.dose_reset()

    with STDIO_LOCK:
        print(f"{serial_number} sampling")

    i = 0
    while RUNNING:  # IO loop
        try:
            data.append(SpecData(time(), rc.spectrum()))
            with STDIO_LOCK:
                print(f"\rn:{i}", end="", flush=True)
                i += 1
            sleep(args.interval)
            tbar()
        except (usb.core.USBError, BrokenBarrierError):
            THREAD_BARRIER.abort()
            RUNNING = False

        if USR1FLAG:  # handle request to snapshot state
            save_data(
                data=data,
                prefix=args.prefix,
                serial_number=serial_number,
                use_pickle=args.pickle,
            )
            with STDIO_LOCK:
                print(f"{serial_number} snapshot")
            tbar()
            USR1FLAG = False

    # loop complete, print summary, save data
    with STDIO_LOCK:
        nd = len(data) - 2
        print(f"{serial_number} data collection stop - {nd} records, {nd*args.interval:.1f}s")

    save_data(
        data=data,
        prefix=args.prefix,
        serial_number=serial_number,
        use_pickle=args.pickle,
    )


def main() -> None:
    global RUNNING

    args = get_args()
    try:
        dev_names = find_radiacode_devices()
    except Exception:
        dev_names = None
    finally:
        if not dev_names:
            print("No devices Found")
            sys.exit(1)

    missing = set(args.devs).difference(set(dev_names))
    if missing:
        if args.require_all:
            print(f"Some devices are missing: {' '.join(list(missing))}")
            sys.exit(1)
        else:
            # Well then, some devices were present, some were requested
            args.devs = list(set(args.devs).intersection(set(dev_names)))

    if not args.devs:  # no devs specified, use all detected
        args.devs = dev_names

    THREAD_BARRIER._parties = len(args.devs)  # ick, but works

    start_time = time()
    # create the threads and store in a list so they can be checked later
    threads: List[Thread] = [
        Thread(
            target=rc_worker,
            name=serial_number,
            args=(args, serial_number, start_time),
        )
        for serial_number in args.devs
    ]

    signal(SIGUSR1, handle_sigusr1)

    # Start the readers
    [t.start() for t in threads]

    # Main process/thread slowly spins waiting for ^C. If interrupt is received, or one of the
    # workers exits, set a shutdown flag which will cause all other threads to gracefully shut
    try:
        while True:
            sleep(1)
            if not all([t.is_alive() for t in threads]):
                raise ChildProcessError
    except ChildProcessError:
        print("Some threads exited early")
    except KeyboardInterrupt:
        # print("Stopping threads")
        pass
    finally:
        RUNNING = False
        with STDIO_LOCK:
            print()

    # Clean up
    while True:
        [t.join(0.1) for t in threads]
        if any([t.is_alive() for t in threads]):
            sleep(0.1)
        else:
            break


if __name__ == "__main__":
    main()
