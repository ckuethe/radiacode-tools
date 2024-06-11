#!/usr/bin/env python3
# Author: Chris Kuethe <chris.kuethe@gmail.com> , https://github.com/ckuethe/radiacode-tools
# SPDX-License-Identifier: MIT

"""
AppMetrics

If you're familiar with varz and other applicaton statistics endpoints,
you'll be right at home here.

Instantiate an AppMetrics object, and you'll get a bonus http server on
localhost serving up the values of metrics controlled by the various
counter, flag, and gauge functions.
"""

import sys
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from json import dumps as jdumps
from os import getpid
from threading import Lock, Thread
from time import monotonic, process_time, time
from typing import Any, Dict, List, Optional, Union

Number = Union[int, float]

# I use these strings so much ...
C: str = "counter"
F: str = "flag"
G: str = "gauge"
P: str = "process"


class AppMetrics:
    """
    An AppMetrics (statistics, varz) server.

    Instantiate a global instance in your app, by the time __init__
    returns, the HTTP listener will already be running.

        ams = AppMetrics(port=12347)

    Some basic process metrics are created:
    - pid
    - process name
    - cputime
    - monitonic run time
    - system time

    Then add some metrics:

        ams.flag_create("my_flag")
        ams.counter_create("my_counter")
        ams.gauge_create("my_gauge")

    Once you have these metrics created, you can update them

        ams.counter_increment("my_counter")
        ams.counter_decrement("my_counter")
        ams.flag_set("my_flag")
        ams.flag_clear("my_flag")
        ams.gauge_update("my_gauge", get_some_value())
    """

    _mtypes: List[str] = [C, F, G]
    _stub = False
    am_mutex: Lock = Lock()

    def __init__(self, port: int = 8274, local_only: bool = True, appname: str = "", stub=False):
        """
        port: tcp port on which to listen
        local_only: whether or not to bind to localhost or wildcard
        appname: identificaton string for metrics
        stub: create a dummy that doesn't do anything, but can at least be used for prototyping
        """
        if stub:
            self._stub = stub
            return
        self._stats: Dict[str, Any] = {P: {"pid": getpid(), "appname": appname}, C: {}, F: {}, G: {}}
        self._init_real_time = monotonic()
        self._wall_time = time()
        self._init_proc_time = process_time()
        self._set_clocks()
        self._server = AppMetricsServer(app_metrics=self, port=port, local_only=local_only)

    def _set_clocks(self):
        """Set the cpu counter elements"""
        self._stats[P]["real"] = monotonic() - self._init_real_time
        self._stats[P]["wall"] = time()
        self._stats[P]["proc"] = process_time() - self._init_proc_time

    def get_stats(self) -> Dict[str, Any]:
        "return a copy of the latest statistics."
        with self.am_mutex:
            self._set_clocks()
            return self._stats.copy()

    # Counters
    def counter_create(self, name: str, init_val: Number = 0):
        return self._create_metric(C, name, init_val)

    def counter_increment(self, name: str, step=1):
        with self.am_mutex:
            self._stats[C][name] += step

    def counter_decrement(self, name: str, step: Number = 1):
        with self.am_mutex:
            self._stats[C][name] -= step

    # Flags
    def flag_create(self, name: str, init_val: bool = False):
        self._create_metric(F, name, init_val)

    def flag_setval(self, name: str, v: bool):
        with self.am_mutex:
            if name not in self._stats[F]:
                raise KeyError(f"flag:{name}")
            if isinstance(v, bool):
                self._stats[F][name] = v
            else:
                raise ValueError

    def flag_set(self, name: str):
        self.flag_setval(name, True)

    def flag_clear(self, name: str):
        self.flag_setval(name, False)

    # Gauges
    def gauge_create(self, name: str, init_val: Number = 0):
        self._create_metric(G, name, init_val)

    def gauge_update(self, name: str, v: Number):
        with self.am_mutex:
            if name not in self._stats[G]:
                raise KeyError(f"gauge:{name}")
            if isinstance(v, int) or isinstance(v, float):
                self._stats[G][name] = v
            else:
                raise ValueError

    def _create_metric(self, mtype: str, name: str, init_val: Any):
        if mtype not in self._mtypes:
            raise ValueError(f"Metric type must be one of {mtype}")
        with self.am_mutex:
            if name not in self._stats[mtype]:
                self._stats[mtype][name] = init_val
            else:
                raise ValueError(f"{mtype}:{name} already exists")


class AppMetricsBaseReqHandler(BaseHTTPRequestHandler):
    """ """

    def __init__(self, metrics: AppMetrics, *args, **kwargs):
        self.metrics = metrics
        super().__init__(*args, **kwargs)

    def do_GET(self):
        encoded = jdumps(self.metrics.get_stats(), indent=1).encode() + b"\r\n"
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(encoded))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: Any) -> None:
        "Ingentional log suppression"
        pass


class AppMetricsServer:
    _server_thread: Optional[Thread] = None

    def __init__(self, app_metrics: AppMetrics, port: int = 8274, local_only: bool = True, appname: str = ""):
        address = "localhost" if local_only else "0.0.0.0"
        self._server_thread = Thread(
            # deepcode ignore MissingAPI: Thread is joined below..
            target=self._make_http_thread,
            args=((address, port), app_metrics),
            daemon=True,
            name="varz_server",
        )
        self._server_thread.start()

    def __del__(self):
        if self._server_thread and isinstance(self._server_thread, Thread):
            self._server_thread.join()
            self._server_thread = None

    def _make_http_thread(self, server_address, metrics: AppMetrics):
        print(f"Starting AppMetrics server on {server_address}", file=sys.stderr)
        AppMetricsReqHandler = partial(AppMetricsBaseReqHandler, metrics)
        self._server = HTTPServer(server_address=server_address, RequestHandlerClass=AppMetricsReqHandler)
        self._server.serve_forever()
