#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

"""
A tool for recording real time count and dose rates, as well as time synchronized
spectra from multiple radiacode devices. These quantities may be geotagged if the
the host running this tool is running a GPSD instance. This allows the production
of Radiacode compatible rctrk (track) and rcspg (spectrogram files); additional
environmental inputs may be supported in the future to allow for enrichment with
sensor altitude, attitude, ambient temperature, humidity...
"""

import os
import socket
import sys
from argparse import ArgumentParser, Namespace
from collections import namedtuple
from datetime import datetime
from json import JSONDecodeError
from json import dumps as jdumps
from json import loads as jloads
from queue import Queue
from re import match as re_match
from signal import SIGINT, signal
from tempfile import mkstemp
from threading import Barrier, BrokenBarrierError, Lock, Thread, active_count
from threading import enumerate as list_threads
from time import gmtime, sleep, strftime, time
from typing import Dict, List, Union

import usb.core
from radiacode import RadiaCode
from radiacode.transports.usb import DeviceNotFound

from rcutils import RtData, SpecData, find_radiacode_devices, specdata_to_dict

Number = Union[int, float]
GpsData = namedtuple("GpsData", ["payload"])

MIN_POLL_INTERVAL: float = 0.5  # internally radiacode seems to do 2Hz updates, but 1Hz may give better results
RC_LOCKS: Dict[str, Lock] = dict()  # prevent rtdata polling and spectrum polling from stomping on each other
STDIO_LOCK: Lock = Lock()  # Prevent stdio corruption
THREAD_BARRIER: Barrier = Barrier(0)  # intialized to 0 to shut up static type checking

# Queues and stuff
DATA_QUEUE: Queue = Queue()  # Global so I can use them in signal handlers
CTRL_QUEUE: Queue = Queue()
SHUTDOWN_OBJECT = object()


def tbar(wait_time=None) -> None:
    """
    Helper to synchronize all threads; when the last one arrives it resets the barrier.

    Optionally accepts a timeout value; if this time elapsed without the barrier being
    reached by the required threads, a BarrierException is raised.
    """
    if 0 == THREAD_BARRIER.wait(wait_time):
        THREAD_BARRIER.reset()


def handle_sigint(_signum=None, _stackframe=None) -> None:
    CTRL_QUEUE.put(SHUTDOWN_OBJECT)


def get_args() -> Namespace:
    "The usual argparse stuff"

    def gte_zero(s):
        f = float(s)
        if f < 0.0:
            raise ValueError("value cannot be less than 0")
        return f

    def _gpsd(s):
        m = re_match(r"^gpsd://(?P<host>[a-zA-Z0-9_.-]+)(:(?P<port>\d+))?(?P<device>/.+)?", s)
        if m:
            return m.groupdict()
        else:
            return None

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
        "-g",
        "--gpsd",
        type=_gpsd,
        metavar="URL",
        help="Connect to specified device, eg. gpsd://localhost:2947/dev/ttyACM0",
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
    rv = ap.parse_args()
    if rv.interval < MIN_POLL_INTERVAL:
        print(f"increasing poll interval to {MIN_POLL_INTERVAL}s")
        rv.interval = MIN_POLL_INTERVAL

    # post-processing stages.
    rv.devs = list(set(rv.devs))
    return rv


def rtdata_worker(rc: RadiaCode, serial_number: str) -> None:
    db = []
    while CTRL_QUEUE.qsize() == 0:  # don't even need to read the item
        sleep(1)
        with RC_LOCKS[serial_number]:
            try:
                db = rc.data_buf()
            except Exception as e:
                z = e.args[0]
                if "seq jump" in z or "but have only" in z:
                    continue
                else:
                    raise

        for x in db:
            rtd_type = x.__class__.__name__  # ick.
            if rtd_type == "Event":
                continue
            d = {
                "time": x.dt.timestamp(),
                "serial_number": serial_number,
                "type": rtd_type,
            }

            xd = x.__dict__
            d.update(
                {
                    f: xd.get(f, None)
                    for f in ["temperature", "charge_level", "count_rate", "dose_rate", "count", "dose", "duration"]
                }
            )
            DATA_QUEUE.put(RtData(**d))


def rc_worker(args: Namespace, serial_number: str) -> None:
    """
    Thread responsible for data acquisition. Connects to devices, polls spectra,
    accumulates data, and generates the output file
    """

    RC_LOCKS[serial_number] = Lock()
    try:
        rc = RadiaCode(serial_number=serial_number)
    except (usb.core.USBTimeoutError, usb.core.USBError, DeviceNotFound) as e:
        with STDIO_LOCK:
            print(f"{serial_number} failed to connect - cable error, device disconnect, bt connected? {e}")
            CTRL_QUEUE.put(SHUTDOWN_OBJECT)  # if we can't start all threads, shut everything down
        return

    with RC_LOCKS[serial_number], STDIO_LOCK:
        rc.set_local_time(datetime.now())
        DATA_QUEUE.put(SpecData(time(), serial_number, rc.spectrum_accum()))
        print(f"{serial_number} Connected ")

    # wait for all threads to connect to their devices
    if THREAD_BARRIER.n_waiting >= 1:
        with STDIO_LOCK:
            print(f"{serial_number} waiting for device connections")

    try:
        tbar(3)
    except BrokenBarrierError:
        with STDIO_LOCK:
            print(f"timeout waiting for devices")
        return

    rtdata_thread = Thread(
        target=rtdata_worker,
        args=(rc, serial_number),
        name=f"rtdata-worker-{serial_number}",
    )
    rtdata_thread.start()

    with RC_LOCKS[serial_number]:
        if args.reset_spectrum:
            rc.spectrum_reset()
        if args.reset_dose:
            rc.dose_reset()

    with STDIO_LOCK:
        print(f"{serial_number} sampling")

    i = 0
    while CTRL_QUEUE.qsize() == 0:  # don't even need to read the item
        try:
            # Grab the spectrum...
            with RC_LOCKS[serial_number]:
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

    log_fds = {d: None for d in args.devs}
    start_time = time()
    time_string = strftime("%Y%m%d%H%M%S", gmtime(start_time))

    for sn in args.devs:
        tmpfd, tmpfn = mkstemp(dir=".")
        os.close(tmpfd)
        fn = f"raw_{sn}_{time_string}.ndjson"
        os.rename(tmpfn, fn)
        # deepcode ignore MissingClose: There is a matching close loop below.. snyk just can't find it
        log_fds[sn] = open(fn, "w")

    running = True
    while running:
        while DATA_QUEUE.qsize():
            msg = DATA_QUEUE.get()
            if msg is SHUTDOWN_OBJECT:
                running = False  # bail out once this batch of messages is done
                continue

            elif isinstance(msg, SpecData):
                fd = log_fds[msg.serial_number]
                print(jdumps(specdata_to_dict(msg)), file=fd, flush=True)

            elif isinstance(msg, RtData):
                fd = log_fds[msg.serial_number]
                print(jdumps(msg._asdict()), file=fd, flush=True)

            elif isinstance(msg, GpsData):
                gps_msg = jdumps(msg.payload)
                for sn in log_fds:
                    print(gps_msg, file=log_fds[sn], flush=True)

            else:
                with STDIO_LOCK:
                    print(f"ignored {msg}")
                pass  # who put this junk here?

        sleep(MIN_POLL_INTERVAL)

    # No longer `running`
    for sn in args.devs:
        if sn in log_fds:
            log_fds[sn].close()
    return


def gps_worker(args: Namespace) -> None:
    """
    Feed position fixes from a GPSD instance into the logs

    GPS data enrichment is ... a polite request. If GPSD goes down, navigation
    solutions are unavailable or invalid, etc. we don't want to take quit the
    whole process.
    """
    srv = (args.gpsd["host"], 2947 if args.gpsd["port"] is None else args.gpsd["port"])
    watch_args = {"enable": True, "json": True}
    if args.gpsd["device"]:
        watch_args["device"] = args.gpsd["device"]
    watch = "?WATCH=" + jdumps(watch_args)
    while CTRL_QUEUE.qsize() == 0:
        try:
            with socket.create_connection(srv, 3) as s:
                gpsfd = s.makefile("rw")
                print(watch, file=gpsfd, flush=True)

                dedup = None
                while CTRL_QUEUE.qsize() == 0:
                    line = gpsfd.readline().strip()
                    try:
                        x = jloads(line)
                        if x["class"] != "TPV":
                            continue
                        if x["time"] == dedup:
                            continue
                        if x["mode"] < 2:
                            continue

                        x["gnss"] = True
                        tpv = GpsData(
                            {
                                f: x.get(f, None)
                                for f in [
                                    "time",
                                    "gnss",
                                    "mode",
                                    "lat",
                                    "lon",
                                    "alt",
                                    "epc",
                                    "sep",
                                    "speed",
                                    "track",
                                    "climb",
                                ]
                            }
                        )
                        DATA_QUEUE.put(tpv)
                    except (KeyError, JSONDecodeError):  # skip bad messages, no fix, etc.
                        pass
                return  # clean exit
        except (socket.error, TimeoutError):
            DATA_QUEUE.put(GpsData(payload='{"gnss": false, "mode": 0}'))
            sleep(1)


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

    expected_thread_count = 2 * len(args.devs)  # two device threads: spectrum and realtime data

    # file deepcode ignore MissingAPI: all threads will be cleaned at the bottom of main()
    Thread(target=log_worker, args=(args,), name="log-worker").start()
    expected_thread_count += 1

    if args.gpsd:
        Thread(target=gps_worker, args=(args,), name="gps-worker").start()
        expected_thread_count += 1

    # create the threads and store in a list so they can be checked later
    [
        Thread(
            target=rc_worker,
            name=f"poller-worker-{serial_number}",
            args=(args, serial_number),
        ).start()
        for serial_number in args.devs
    ]

    THREAD_BARRIER._parties = len(args.devs)
    signal(SIGINT, handle_sigint)

    sleep(1)

    # Main process/thread slowly spins waiting for ^C. If interrupt is received, or one of the
    # workers exits, set a shutdown flag which will cause all other threads to gracefully shut
    try:
        while active_count() >= expected_thread_count:
            sleep(MIN_POLL_INTERVAL)
    except KeyboardInterrupt:
        pass
    finally:
        CTRL_QUEUE.put(SHUTDOWN_OBJECT)
        DATA_QUEUE.put(SHUTDOWN_OBJECT)
        with STDIO_LOCK:
            print("Stopping threads")

    # Clean up
    while active_count() > 1:  # main process counts as a thread
        try:
            [t.join(0.1) for t in list_threads()]
        except RuntimeError:
            pass
        sleep(0.1)


if __name__ == "__main__":
    main()
