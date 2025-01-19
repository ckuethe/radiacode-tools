#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# Author: Chris Kuethe <chris.kuethe@gmail.com> , https://github.com/ckuethe/radiacode-tools
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
from argparse import ArgumentParser, Namespace
from datetime import datetime
from json import JSONDecodeError
from json import dumps as jdumps
from json import loads as jloads
from queue import Queue
from re import match as re_match
from signal import SIGHUP, SIGINT, signal
from sys import exit, stderr, stdout
from tempfile import mkstemp
from threading import Barrier, BrokenBarrierError, Lock, Thread, active_count
from threading import enumerate as list_threads
from time import gmtime, sleep, strftime, time
from typing import Dict, TextIO

import usb.core
from radiacode import RadiaCode
from radiacode.transports.usb import DeviceNotFound

from appmetrics import AppMetrics
from rctypes import GpsData, RtData, SpecData
from rcutils import find_radiacode_devices, specdata_to_dict

ams = AppMetrics(stub=True)

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


def handle_shutdown_signal(_signum=None, _stackframe=None) -> None:
    "Signal handler to trigger clean shutdown"
    with STDIO_LOCK:
        print("", file=stderr)
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
    ap.add_argument(
        "--reset-clock",
        action="store_true",
        default=False,
        help="Set the radiacode clock to system time",
    )
    ap.add_argument(
        "--stdout",
        default=False,
        action="store_true",
        help="log to stdout instead of to a file",
    )
    ap.add_argument(
        "--poweroff",
        action="store_true",
        default=False,
        help="Turn off radiacode devices when this program exits",
    )
    rv = ap.parse_args()
    if rv.interval < MIN_POLL_INTERVAL:
        print(f"increasing poll interval to {MIN_POLL_INTERVAL}s", file=stderr)
        rv.interval = MIN_POLL_INTERVAL

    # post-processing stages.
    rv.devs = list(set(rv.devs))
    return rv


def rtdata_worker(rc: RadiaCode, serial_number: str) -> None:
    """
    RadiaCode emits some real-time data (databuf) and as it is available it gets
    logged, in particular dose, count, and their rates. These are used to build
    tracks.
    """
    with STDIO_LOCK:
        print("Starting rtdata_worker", file=stderr)
    db = []
    while CTRL_QUEUE.qsize() == 0:  # don't even need to read the item
        sleep(1)
        with RC_LOCKS[serial_number]:
            try:
                db = rc.data_buf()
            except Exception as e:
                z = str(e.args[0])
                print(f"rtdata_worker caught exception {z}")
                if "seq jump" in z or "but have only" in z:
                    sleep(0.1)
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
            for f in ["dose", "count", "dose_rate", "count_rate"]:
                if f in d and d[f] is not None:
                    ams.gauge_update(f"{f}_{serial_number}", d[f])

            DATA_QUEUE.put(RtData(**d))
    with STDIO_LOCK:
        print("Exiting rtdata_worker", file=stderr)
    return


def rc_worker(args: Namespace, serial_number: str) -> None:
    """
    Thread responsible for data acquisition. Connects to devices, polls spectra,
    accumulates data, and generates the output file
    """
    ams.counter_create(f"num_reports_{serial_number}")
    ams.gauge_create(f"dose_{serial_number}")
    ams.gauge_create(f"count_{serial_number}")
    ams.gauge_create(f"dose_rate_{serial_number}")
    ams.gauge_create(f"count_rate_{serial_number}")
    RC_LOCKS[serial_number] = Lock()
    try:
        rc = RadiaCode(serial_number=serial_number)
    except (usb.core.USBTimeoutError, usb.core.USBError, DeviceNotFound) as e:
        with STDIO_LOCK:
            print(
                f"{serial_number} failed to connect - cable error, device disconnect, bt connected? {e}",
                file=stderr,
            )
            CTRL_QUEUE.put(SHUTDOWN_OBJECT)  # if we can't start all threads, shut everything down
        return

    try:
        # radiacode will enumerate and give some information like serial number
        # and calibration if it's turned off, but won't return a useful spectrum.
        # Ask me how much data I've lost because of this. :(
        rc.set_device_on(True)
    except AssertionError as e:
        # versions of cdump/radiacode <= 0.3.3 throw an assertion error if you try
        # to turn the device on. I've sent a PR to allow this to work.
        with STDIO_LOCK:
            print(
                f"WARNING: unable to turn device {serial_number} on. Upgrade to radiacode>=0.3.4 or data may be lost."
            )

    with RC_LOCKS[serial_number], STDIO_LOCK:
        if args.reset_clock:
            rc.set_local_time(datetime.now())
        DATA_QUEUE.put(SpecData(time(), serial_number, rc.spectrum_accum()))
        print(f"{serial_number} Connected ", file=stderr)

    # wait for all threads to connect to their devices
    try:
        tbar(10)
    except BrokenBarrierError:
        with STDIO_LOCK:
            print(f"timeout waiting for all devices to connect", file=stderr)
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
        print(f"{serial_number} sampling", file=stderr)

    samples = 0
    while CTRL_QUEUE.qsize() == 0:  # don't even need to read the item
        try:
            # Grab the spectrum...
            with RC_LOCKS[serial_number]:
                # FIXME figure out a way to augment with monotonic time
                sd = SpecData(time(), serial_number, rc.spectrum())
                DATA_QUEUE.put(sd)
                ams.counter_increment(f"num_reports_{serial_number}")
                ams.gauge_update(f"count_{serial_number}", sum(sd.spectrum.counts))
            with STDIO_LOCK:
                print(f"\rn:{samples}", end="", flush=True, file=stderr)
                samples += 1
            sleep(args.interval)
            tbar()
        except (usb.core.USBError, BrokenBarrierError):
            # once running though, don't take down all the other threads
            THREAD_BARRIER.abort()

    with STDIO_LOCK:
        print(f"{serial_number} data collection stop - {samples} records, {samples*args.interval:.1f}s", file=stderr)

    if args.poweroff:
        rc.set_device_on(False)


def log_worker(args: Namespace) -> None:
    """
    Handle realtime logging of measurements so you don't have to wait for a spectrogram
    file to be written, and the reader threads don't have to wait on disk.
    """
    with STDIO_LOCK:
        print(f"starting log_worker for: {' '.join(args.devs)}", file=stderr)

    log_fds: Dict[str, TextIO] = {}  # {d: None for d in args.devs}
    start_time = time()
    time_string = strftime("%Y%m%d%H%M%S", gmtime(start_time))

    for sn in args.devs:
        if args.stdout:
            log_fds[sn] = stdout
        else:
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
            if log_fds[sn] != stdout:
                log_fds[sn].close()
    return


def gps_worker(args: Namespace) -> None:
    """
    Feed position fixes from a GPSD instance into the logs

    GPS data enrichment is ... a polite request. If GPSD goes down, navigation
    solutions are unavailable or invalid, etc. we don't want to take quit the
    whole process.
    """
    ams.gauge_create("latitude")
    ams.gauge_create("longitude")
    ams.gauge_create("altitude")
    ams.gauge_create("gps_mode")
    ams.gauge_create("sats_seen")
    ams.gauge_create("sats_used")
    gps_fields = ["time", "gnss", "mode", "lat", "lon", "alt", "epc", "sep", "speed", "track", "climb"]
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
                ams.flag_set("gps_connected")
                dedup = None
                while CTRL_QUEUE.qsize() == 0:  # Check the control queue every line
                    line = gpsfd.readline().strip()
                    try:
                        x = jloads(line)
                        if x["class"] == "SKY":
                            try:
                                ams.gauge_update("sats_seen", int(x["nSat"]))
                                ams.gauge_update("sats_used", int(x["uSat"]))
                            except KeyError:
                                pass
                        if x["class"] != "TPV":
                            continue
                        if x["time"] == dedup:
                            continue
                        dedup = x["time"]
                        ams.gauge_update("gps_mode", x["mode"])
                        if x["mode"] < 2:
                            continue

                        x["gnss"] = True
                        tpv = GpsData({f: x.get(f, None) for f in gps_fields})
                        ams.gauge_update("latitude", tpv.payload["lat"])
                        ams.gauge_update("longitude", tpv.payload["lon"])
                        ams.gauge_update("altitude", tpv.payload.get("alt", -6378))
                        DATA_QUEUE.put(tpv)
                    except (KeyError, JSONDecodeError) as e:  # skip bad messages, no fix, etc.
                        print(f"JSON processing error {e} in gps thread", file=stderr)
                        pass
                # Control Queue is non-empty, shutting down
                ams.flag_clear("gps_connected")
                return  # clean exit
        except (socket.error, TimeoutError) as e:
            DATA_QUEUE.put(GpsData(payload='{"gnss": false, "mode": 0}'))
            with STDIO_LOCK:
                if e.errno != 111:  # FIXME is ECONNREFUSED always 111? Is there a macro?
                    print(f"caught exception {e} in gps thread", file=stderr)
            sleep(1)
    #
    ams.flag_clear("gps_connected")
    return  # clean exit


def main() -> None:
    args = get_args()
    global ams

    ams = AppMetrics(port=6853, local_only=False, appname="rcmultispg")
    ams.flag_create("gps_connected")
    try:
        dev_names = find_radiacode_devices()
    except Exception:
        dev_names = None
    finally:
        if not dev_names:
            print("No devices Found", file=stderr)
            exit(1)

    missing = set(args.devs).difference(set(dev_names))
    if missing:
        if args.require_all:
            print(f"Some devices are missing: {' '.join(list(missing))}", file=stderr)
            exit(1)
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

    THREAD_BARRIER._parties = len(args.devs)
    signal(SIGINT, handle_shutdown_signal)
    # appmetrics will SIGHUP the parent process when you hit the /quitquitquit
    # endpoint. catch it here in the same way as we catch SIGINT to shut down
    # logging cleanly. This also will power down connected radiacode devices to
    # save batteries.
    signal(SIGHUP, handle_shutdown_signal)
    # create the threads and store in a list so they can be checked later
    threads = [
        Thread(
            target=rc_worker,
            name=f"poller-worker-{serial_number}",
            args=(args, serial_number),
        )
        for serial_number in args.devs
    ]
    [t.start() for t in threads]
    while active_count() < expected_thread_count:
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
            print("Stopping threads", file=stderr)

    # Clean up
    ams.close()
    while active_count() > 1:  # main process counts as a thread
        try:
            [t.join(0.1) for t in list_threads() if t.name != "MainThread"]
            # FIXME print what we're still waiting for
        except RuntimeError:
            pass
        sleep(0.1)


if __name__ == "__main__":
    main()
