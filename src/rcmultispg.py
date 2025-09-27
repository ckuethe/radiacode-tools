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
import sys
from argparse import ArgumentParser, Namespace
from datetime import datetime
from json import dumps as jdumps
from json import loads as jloads
from queue import Queue
from signal import SIGHUP, SIGINT, SIGTERM, signal
from tempfile import mkstemp
from threading import Barrier, BrokenBarrierError, Lock, Thread, active_count
from threading import enumerate as list_threads
from time import gmtime, monotonic, sleep, strftime, time
from typing import Any, Dict, List, TextIO, Tuple

import usb.core  # type: ignore
from radiacode import RadiaCode  # type: ignore
from radiacode.transports.usb import DeviceNotFound  # type: ignore

from radiacode_tools.appmetrics import AppMetrics  # type: ignore
from radiacode_tools.rc_types import GpsData, RcJSONEncoder, RtData, SpecData
from radiacode_tools.rc_utils import UTC, find_radiacode_devices
from radiacode_tools.rc_validators import _gpsd

ams: AppMetrics = AppMetrics(stub=True)

# According to radiacode.configuration(), DeviceParams.MinFrmPeriod_ms is 500.
# I assume that means 2Hz internal data update rate, which also tracks with
# search mode producing up to 2 measurements per second.
MIN_POLL_INTERVAL: float = 0.5
RC_LOCKS: Dict[str, Lock] = dict()  # prevent rtdata polling and spectrum polling from stomping on each other
STDIO_LOCK: Lock = Lock()  # Prevent stdio corruption
THREAD_BARRIER: Barrier = Barrier(0)

# Queues and stuff
DATA_QUEUE: Queue[Any] = Queue()  # Global so I can use them in signal handlers
CTRL_QUEUE: Queue[Any] = Queue()
SHUTDOWN_OBJECT: object = object()


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
        print("\ngot shutdown signal", file=sys.stderr)
    CTRL_QUEUE.put(SHUTDOWN_OBJECT)
    DATA_QUEUE.put(SHUTDOWN_OBJECT)


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
        print(f"increasing poll interval to {MIN_POLL_INTERVAL}s", file=sys.stderr)
        rv.interval = MIN_POLL_INTERVAL

    # post-processing stages.
    rv.devs = list(set(rv.devs))
    return rv


def rtdata_worker(rc: RadiaCode, serial_number: str) -> None:
    """
    RadiaCode emits some real-time data (databuf) and as it is available it gets
    logged, in particular dose, count, and their rates. These are used to build
    tracks.

    Caution: this will download whatever's in the data buffer which could be days
    and days of history. You'll need to sort and filter out events that happened
    before the current recording session.
    """
    with STDIO_LOCK:
        print(f"Starting rtdata_worker for {serial_number}", file=sys.stderr)
    db = []
    while CTRL_QUEUE.qsize() == 0:  # don't even need to read the item
        sleep(1)
        with RC_LOCKS[serial_number]:
            try:
                db = rc.data_buf()
            except KeyboardInterrupt:
                return
            except Exception as e:
                # FIXME this needs to do some better decoding of the exception
                # that might mean I need to propagate a better error message up
                z = str(e.args[0])
                if "seq jump" not in z:
                    with STDIO_LOCK:
                        print(f"rtdata_worker {serial_number} caught exception {z}", file=sys.stderr)
                continue

        for rec in db:
            rtd_type = rec.__class__.__name__  # ick.
            if rtd_type == "Event":
                continue
            rtdata_msg: dict[str, Any] = {
                "monotime": monotonic(),
                "dt": rec.dt,
                "serial_number": serial_number,
                "type": rtd_type,
            }

            rec_dict: dict[str, Any] = rec.__dict__
            rtdata_msg.update(
                {
                    field: rec_dict.get(field, None)
                    for field in ["temperature", "charge_level", "count_rate", "dose_rate", "count", "dose", "duration"]
                }
            )
            for field in ["dose", "count", "dose_rate", "count_rate"]:
                if field in rtdata_msg and rtdata_msg[field] is not None:
                    ams.gauge_update(f"{field}_{serial_number}", rtdata_msg[field])

            DATA_QUEUE.put(RtData(**rtdata_msg))
    with STDIO_LOCK:
        print(f"Exiting rtdata_worker {serial_number}", file=sys.stderr)
    return


def rc_worker(args: Namespace, serial_number: str) -> bool:
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
        rc: RadiaCode = RadiaCode(serial_number=serial_number)
    except (usb.core.USBTimeoutError, usb.core.USBError, DeviceNotFound) as e:
        # device failed to connect. I'm not sure why this happens (maybe power issues) on my
        # NanoPi, but when it does, I should probably do something like gracefully terminate
        # the threads associated with the failed device, and carry on...
        with STDIO_LOCK:
            print(
                f"{serial_number} failed to connect - cable error, device disconnect, bt connected? {e}",
                file=sys.stderr,
            )
            del RC_LOCKS[serial_number]
            if args.require_all:
                print(
                    f"Missing required device {serial_number} - shutting down",
                    file=sys.stderr,
                )
                CTRL_QUEUE.put(SHUTDOWN_OBJECT)  # if we can't start all threads, shut everything down
        return False

    # radiacode will enumerate and give some information like serial number
    # and calibration if it's turned off, but won't return a useful spectrum.
    # Ask me how much data I've lost because of this. :( Turning the device
    # on requires radiacode>=0.3.4
    rc.set_device_on(True)

    with RC_LOCKS[serial_number]:
        DATA_QUEUE.put(
            SpecData(
                monotime=monotonic(),
                dt=datetime.now(tz=UTC),
                serial_number=serial_number,
                spectrum=rc.spectrum_accum(),  # type: ignore - pylance doesn't understand what I'm doing here
            )
        )
    with STDIO_LOCK:
        print(f"{serial_number} Connected ", file=sys.stderr)

    # wait for all threads to connect to their devices
    try:
        tbar(10)
    except BrokenBarrierError:
        with STDIO_LOCK:
            print("timeout waiting for all devices to connect", file=sys.stderr)
            CTRL_QUEUE.put(SHUTDOWN_OBJECT)
            args.devs.remove(serial_number)
            THREAD_BARRIER._parties -= 1  # type: ignore - Evil, but there's no other way to adjust this
        return False

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
        print(f"{serial_number} sampling", file=sys.stderr)

    samples = 0
    while CTRL_QUEUE.qsize() == 0:  # don't even need to read the item
        try:
            # Grab the spectrum...
            with RC_LOCKS[serial_number]:
                sd = SpecData(
                    monotime=monotonic(),
                    dt=datetime.now(tz=UTC),
                    serial_number=serial_number,
                    spectrum=rc.spectrum(),
                )
            DATA_QUEUE.put(sd)
            ams.counter_increment(f"num_reports_{serial_number}")
            ams.gauge_update(f"count_{serial_number}", sum(sd.spectrum.counts))
            with STDIO_LOCK:
                print(f"\rn:{samples}", end="", flush=True, file=sys.stderr)
                samples += 1
            sleep(args.interval)
            tbar()
        except (usb.core.USBError, BrokenBarrierError):
            # once running though, don't take down all the other threads
            THREAD_BARRIER.abort()

    if args.poweroff:
        rc.set_device_on(False)

    with STDIO_LOCK:
        print(
            f"{serial_number} data collection stop - {samples} records, {samples * args.interval:.1f}s", file=sys.stderr
        )

    return True


def log_worker(args: Namespace) -> None:
    """
    Handle realtime logging of measurements so you don't have to wait for a spectrogram
    file to be written, and the reader threads don't have to wait on disk.
    """
    with STDIO_LOCK:
        print(f"starting log_worker for: {' '.join(args.devs)}", file=sys.stderr)

    log_fds: Dict[str, TextIO] = {}  # {d: None for d in args.devs}
    start_time = time()
    time_string = strftime("%Y%m%d%H%M%S", gmtime(start_time))

    for sn in args.devs:
        if args.stdout:
            log_fds[sn] = sys.stdout
        else:
            tmpfd, tmpfn = mkstemp(dir=".")
            os.close(tmpfd)
            fn = f"raw_{sn}_{time_string}.ndjson"
            os.rename(tmpfn, fn)
            # deepcode ignore MissingClose: There is a matching close loop below.. snyk just can't find it
            log_fds[sn] = open(fn, "w")

    enc = RcJSONEncoder()
    running = True
    while running:
        while DATA_QUEUE.qsize():
            msg = DATA_QUEUE.get()
            if msg is SHUTDOWN_OBJECT:
                running = False  # bail out once this batch of messages is done
                with STDIO_LOCK:
                    print("log_worker detected SHUTDOWN_OBJECT, scheduling shutdown")
                continue

            elif isinstance(msg, SpecData):
                fd = log_fds[msg.serial_number]
                print(enc.encode(msg), file=fd, flush=True)

            elif isinstance(msg, RtData):
                fd = log_fds[msg.serial_number]
                print(enc.encode(msg), file=fd, flush=True)

            elif isinstance(msg, GpsData):
                for sn in log_fds:
                    print(enc.encode(msg), file=log_fds[sn], flush=True)

            else:
                with STDIO_LOCK:
                    print(f"ignored {msg}", file=sys.stderr)
                pass  # who put this junk here?

        sleep(MIN_POLL_INTERVAL)

    # No longer `running`
    for sn in args.devs:
        if sn in log_fds:
            if log_fds[sn] != sys.stdout:
                log_fds[sn].close()
    with STDIO_LOCK:
        print("log worker shutting down", file=sys.stderr)
    return


def gps_worker(args: Namespace) -> None:
    """
    Feed position fixes from a GPSD instance into the logs

    GPS data enrichment is ... a polite request. If GPSD goes down, navigation
    solutions are unavailable or invalid, etc. we don't want to take quit the
    whole process.
    """
    BAD_GPS_ALT: float = -6378  # center of earth
    DFLT_GPSD_PORT: int = 2947
    ams.flag_create("gps_connected")
    ams.gauge_create("latitude")
    ams.gauge_create("longitude")
    ams.gauge_create("altitude")
    ams.gauge_create("gps_mode")
    ams.gauge_create("sats_seen")
    ams.gauge_create("sats_used")
    # time in the GPS field is as reported by the GNSS receiver, and may (will) differ from host time
    gps_fields: list[str] = ["time", "gnss", "mode", "lat", "lon", "alt", "epc", "sep", "speed", "track", "climb"]
    srv: tuple[str, int] = (args.gpsd["host"], DFLT_GPSD_PORT if args.gpsd["port"] is None else args.gpsd["port"])
    watch_args: dict[str, bool | str] = {"enable": True, "json": True}
    if args.gpsd["device"]:
        watch_args["device"] = args.gpsd["device"]
    watch: str = "?WATCH=" + jdumps(watch_args)
    exstr = ""
    while CTRL_QUEUE.qsize() == 0:  # reconnect loop
        try:
            with socket.create_connection(srv, timeout=3) as s:
                s.setblocking(False)
                with s.makefile("rw") as gpsfd:
                    print(watch, file=gpsfd, flush=True)
                    ams.flag_set("gps_connected")
                    dedup = None
                    while True:
                        sleep(0.1)
                        line: str = gpsfd.readline().strip()
                        try:
                            if "No such device" in line:
                                raise IOError("GPSD is confused")
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
                            tpv: GpsData = GpsData(
                                monotime=monotonic(), payload={f: x.get(f, None) for f in gps_fields}
                            )
                            ams.gauge_update("latitude", tpv.payload["lat"])
                            ams.gauge_update("longitude", tpv.payload["lon"])
                            ams.gauge_update("altitude", tpv.payload.get("alt", BAD_GPS_ALT))
                            tpv.payload["hosttime"] = time()
                            DATA_QUEUE.put(tpv)
                        except (ValueError, KeyError):  # skip no fix, etc.
                            pass

                        # Control Queue is non-empty, shutting down
                        if CTRL_QUEUE.qsize():  # Check the control queue every line
                            ams.flag_clear("gps_connected")
                            return  # clean exit
        except KeyboardInterrupt:
            CTRL_QUEUE.put(SHUTDOWN_OBJECT)
            ams.flag_clear("gps_connected")
            return
        except Exception as e:  # network error, complete garbage... give up and reconnect
            exstr = str(e)
        finally:
            DATA_QUEUE.put(GpsData(monotime=monotonic(), payload={"gnss": False, "mode": 0, "error": exstr}))
            with STDIO_LOCK:
                # if e.errno != 111:  # FIXME is ECONNREFUSED always 111? Is there a macro?
                if "Connection refused" not in exstr:
                    print(f"caught exception {exstr} in gps thread, reconnecting", file=sys.stderr)
            sleep(1)
    # end reconnect loop

    with STDIO_LOCK:
        print("gps worker shutting down", file=sys.stderr)
    ams.flag_clear("gps_connected")
    return  # clean exit


def create_threads(args: Namespace) -> Tuple[int, List[Thread]]:
    thread_list: List[Thread] = []
    thread_count = 0

    # file deepcode ignore MissingAPI: all threads will be cleaned at the bottom of main()
    log_thread = Thread(target=log_worker, args=(args,), name="log-worker")
    thread_list.append(log_thread)
    log_thread.start()
    thread_count += 1

    if args.gpsd:
        gps_thread = Thread(target=gps_worker, args=(args,), name="gps-worker")
        thread_list.append(gps_thread)
        gps_thread.start()
        thread_count += 1
    else:
        ams.flag_create("gps_connected")
        ams.gauge_create("gps_mode")
        ams.gauge_create("sats_seen")
        ams.gauge_create("sats_used")

    for serial_number in args.devs:
        rc_thread = Thread(
            target=rc_worker,
            name=f"poller-worker-{serial_number}",
            args=(args, serial_number),
        )
        thread_count += 2  # two device threads: spectrum and realtime data
        thread_list.append(rc_thread)
    return thread_count, thread_list


def main() -> None:
    args = get_args()
    global ams
    global THREAD_BARRIER

    dev_names = None
    try:
        dev_names = find_radiacode_devices()
    except Exception:
        pass
    finally:
        if not dev_names:
            print("No devices Found", file=sys.stderr)
            sys.exit(1)

    ams = AppMetrics(port=6853, local_only=False, appname="rcmultispg")
    missing = set(args.devs).difference(set(dev_names))
    if missing:
        if args.require_all:
            print(f"Some devices are missing: {' '.join(list(missing))}", file=sys.stderr)
            sys.exit(1)
        else:
            # Well then, some devices were present, some were requested
            args.devs = list(set(args.devs).intersection(set(dev_names)))

    if not args.devs:  # no devs specified, use all detected
        args.devs = dev_names

    expected_thread_count, thread_list = create_threads(args)

    THREAD_BARRIER = Barrier(len(args.devs))
    signal(SIGINT, handle_shutdown_signal)
    # appmetrics will SIGHUP the parent process when you hit the /quitquitquit
    # endpoint. catch it here in the same way as we catch SIGINT to shut down
    # logging cleanly. This also will power down connected radiacode devices to
    # save batteries.
    signal(SIGHUP, handle_shutdown_signal)
    # create the threads and store in a list so they can be checked later
    [t.start() for t in thread_list if t.name.startswith("poller-worker")]  # type: ignore[func-returns-value]
    retries = 10
    threads_waiting = True
    while threads_waiting:
        nthreads = active_count()
        if nthreads >= expected_thread_count:
            threads_waiting = False
            break
        else:
            with STDIO_LOCK:
                print(f"waiting for ({expected_thread_count - nthreads}) threads to start")
            retries -= 1
            if retries > 0:
                sleep(1)
            else:
                os.killpg(os.getpgrp(), SIGTERM)
                exit()

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
            print("Stopping threads", file=sys.stderr)

    # Clean up
    ams.close()
    while True:
        nt = active_count()
        if nt < 2:  # main process counts as a thread
            break

        try:
            [t.join(0.1) for t in list_threads() if t.name != "MainThread"]  # type: ignore[func-returns-value]
            # FIXME print what we're still waiting for
        except RuntimeError:
            pass

        with STDIO_LOCK:
            print(f"{[t.name for t in list_threads()]}", file=sys.stderr)
        sleep(0.5)


if __name__ == "__main__":
    main()
