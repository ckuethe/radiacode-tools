#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

"A tool for grabbing spectra from multiple radiacode devices at the same time"

import usb.core
from argparse import ArgumentParser, Namespace
from radiacode import RadiaCode, Spectrum
from radiacode.transports.usb import DeviceNotFound
from threading import Barrier, BrokenBarrierError, Thread, Lock, active_count
from queue import Queue
from tempfile import mkstemp
from rcutils import UnixTime2FileTime, find_radiacode_devices
from time import sleep, time, strftime, gmtime
from binascii import hexlify
from collections import namedtuple
from struct import pack as struct_pack
from re import sub as re_sub
from typing import List, Union
from json import dumps as jdumps
from signal import signal, SIGUSR1, SIGINT, SIGALRM, alarm
import sys
import os

Number = Union[int, float]
SpecData = namedtuple("SpecData", ["time", "serial_number", "spectrum"])
MIN_POLL_INTERVAL: float = 0.5
CHECKPOINT_INTERVAL: int = 0
STDIO_LOCK: Lock = Lock()  # Prevent stdio corruption
THREAD_BARRIER: Barrier = Barrier(0)  # intialized to 0 to shut up static type checking

# Queues and stuff
DATA_QUEUE: Queue = Queue()  # Global so I can use them in signal handlers
CTRL_QUEUE: Queue = Queue()
SHUTDOWN_OBJECT = object()
SNAPSHOT_OBJECT = object()


def tbar(wait_time=None) -> None:
    """
    Helper to synchronize all threads; when the last one arrives it resets the barrier.

    Optionally accepts a timeout value; if this time elapsed without the barrier being
    reached by the required threads, a BarrierException is raised.
    """
    if 0 == THREAD_BARRIER.wait(wait_time):
        THREAD_BARRIER.reset()


def handle_sigalrm(_signum=None, _stackframe=None):
    alarm(CHECKPOINT_INTERVAL)
    DATA_QUEUE.put(SNAPSHOT_OBJECT)


def handle_sigusr1(_signum=None, _stackframe=None):
    DATA_QUEUE.put(SNAPSHOT_OBJECT)


def handle_sigint(_signum=None, _stackframe=None):
    CTRL_QUEUE.put(SHUTDOWN_OBJECT)


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
        "-k",
        "--checkpoint-interval",
        type=gte_zero,
        metavar="INT",
        default=0,
        help="Checkpoint interval in seconds",
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
        "-l",
        "--raw-log",
        default=False,
        action="store_true",
        help="record raw measurements to raw_{serial}_{timestamp}.ndjson",
    )

    rv = ap.parse_args()
    if rv.interval < MIN_POLL_INTERVAL:
        print(f"increasing poll interval to {MIN_POLL_INTERVAL}s")
        rv.interval = MIN_POLL_INTERVAL

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


def make_rec(data: SpecData):
    "Turn a SpecData into an easily jsonified dict"
    rec = {
        "timestamp": data.time,
        "serial_number": data.serial_number,
        "duration": data.spectrum.duration.total_seconds(),
        "calibration": [data.spectrum.a0, data.spectrum.a1, data.spectrum.a2],
        "counts": data.spectrum.counts,
    }
    return rec


def save_data(
    data: List[SpecData],
    serial_number: str,
    prefix: str = "rcmulti_",
):
    duration = data[-1].time - data[2].time
    start_time = data[0].time
    time_string = strftime("%Y%m%d%H%M%S", gmtime(start_time))
    fn = f"{prefix}{serial_number}_{time_string}.rcspg"

    header = make_spectrogram_header(
        duration=duration,
        serial_number=serial_number,
        start_time=start_time,
    )
    with STDIO_LOCK:
        print(f"saving spectrogram in {fn}")

    tfd, tfn = mkstemp(dir=".")
    os.close(tfd)
    with open(tfn, "w") as ofd:
        print(header, file=ofd)
        print(make_spectrum_line(data[-1].spectrum), file=ofd)
        print(format_spectra(data), file=ofd)
    os.rename(tfn, fn)


def rc_worker(args: Namespace, serial_number: str) -> None:
    """
    Thread responsible for data acquisition. Connects to devices, polls spectra,
    accumulates data, and generates the output file
    """

    try:
        rc = RadiaCode(serial_number=serial_number)
    except (usb.core.USBTimeoutError, usb.core.USBError, DeviceNotFound) as e:
        with STDIO_LOCK:
            print(f"{serial_number} failed to connect - cable error, device disconnect, bt connected? {e}")
            CTRL_QUEUE.put(SHUTDOWN_OBJECT)  # if we can't start all threads, shut everything down
        return

    with STDIO_LOCK:
        print(f"{serial_number} Connected ")
    DATA_QUEUE.put(SpecData(time(), serial_number, rc.spectrum_accum()))

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
    while CTRL_QUEUE.qsize() == 0:  # don't even need to read the item
        try:
            DATA_QUEUE.put(SpecData(time(), serial_number, rc.spectrum()))
            with STDIO_LOCK:
                print(f"\rn:{i}", end="", flush=True)
                i += 1
            sleep(args.interval)
            tbar()
        except (usb.core.USBError, BrokenBarrierError):
            # once running though, don't take down all the other threads
            THREAD_BARRIER.abort()

    with STDIO_LOCK:
        print(f"{serial_number} data collection stop - {i} records, {i*args.interval:.1f}s")


def log_worker(args: Namespace) -> None:
    "Handle realtime logging of measurements if you can't wait for the spectrogram file"
    with STDIO_LOCK:
        print(f"starting log_worker for: {' '.join(args.devs)}")

    log_fds = {d: None for d in args.devs} if args.raw_log else {}
    measurements = {d: [] for d in args.devs}
    start_time = time()
    time_string = strftime("%Y%m%d%H%M%S", gmtime(start_time))

    for sn in args.devs:
        tmpfd, tmpfn = mkstemp(dir=".")
        os.close(tmpfd)
        fn = f"raw_{sn}_{time_string}.ndjson"
        os.rename(tmpfn, fn)
        log_fds[sn] = open(fn, "w")

    running = True
    snapshot = False
    while running:
        while DATA_QUEUE.qsize():
            msg = DATA_QUEUE.get()
            if msg is SHUTDOWN_OBJECT:
                running = False  # bail out once this batch of messages is done
                continue

            elif msg is SNAPSHOT_OBJECT:
                snapshot = True  # save the current spectrogram immediately
                continue

            elif isinstance(msg, SpecData):
                measurements[msg.serial_number].append(msg)
                if args.raw_log:
                    fd = log_fds[msg.serial_number]
                    print(jdumps(make_rec(msg)), file=fd, flush=True)

            else:
                pass  # who put this junk here?
        if snapshot:
            with STDIO_LOCK:
                print()
            for sn in measurements:
                save_data(data=measurements[sn], serial_number=sn)
            snapshot = False
        sleep(MIN_POLL_INTERVAL / 2)

    for sn in args.devs:
        save_data(data=measurements[sn], serial_number=sn)
        if sn in log_fds:
            log_fds[sn].close()
    return


def main() -> None:
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

    # create the threads and store in a list so they can be checked later
    threads: List[Thread] = [
        Thread(
            target=rc_worker,
            name=serial_number,
            args=(args, serial_number),
        )
        for serial_number in args.devs
    ]

    threads.append(Thread(target=log_worker, args=(args,)))

    signal(SIGUSR1, handle_sigusr1)
    signal(SIGALRM, handle_sigalrm)
    signal(SIGINT, handle_sigint)
    print(f"`kill -USR1 {os.getpid()}` to snapshot the spectrogram")

    # Start the readers
    [t.start() for t in threads]

    sleep(MIN_POLL_INTERVAL)

    if args.checkpoint_interval:
        global CHECKPOINT_INTERVAL
        CHECKPOINT_INTERVAL = int(args.checkpoint_interval)
        alarm(CHECKPOINT_INTERVAL)

    # Main process/thread slowly spins waiting for ^C. If interrupt is received, or one of the
    # workers exits, set a shutdown flag which will cause all other threads to gracefully shut
    try:
        while active_count() - 1 == len(threads):
            sleep(0.25)
    except KeyboardInterrupt:
        pass
    finally:
        CTRL_QUEUE.put(SHUTDOWN_OBJECT)
        DATA_QUEUE.put(SHUTDOWN_OBJECT)
        with STDIO_LOCK:
            print("Stopping threads")

    # Clean up
    while active_count() > 1:  # main process counts as a thread
        [t.join(0.1) for t in threads]
        sleep(0.1)


if __name__ == "__main__":
    main()
