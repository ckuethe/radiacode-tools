#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
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
from http.server import BaseHTTPRequestHandler, HTTPServer, HTTPStatus
from json import dumps as jdumps
from os import getpgrp, getppid, killpg
from signal import SIGHUP
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

    Parameters:
    port: TCP port on which to listen [8274]
    local_only: bind to localhost, or expose externally [True]
    appname: optional name of app to use [""]
    stub: use this to declare the AMx server without starting the http server [False]
    safe: slight protection from accidental /quitquitquit by requiring the PID as the query string [True]

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

    def __init__(
        self, port: int = 8274, local_only: bool = True, appname: str = "", stub: bool = False, safe: bool = True
    ):
        """
        port: tcp port on which to listen
        local_only: whether or not to bind to localhost or wildcard
        appname: identificaton string for metrics
        stub: create a dummy that doesn't do anything, but can at least be used for prototyping
        """
        self._stub = False
        self.am_mutex: Lock = Lock()
        self._stats: Dict[str, Any] = {P: {"pid": getppid(), "appname": appname}, C: {}, F: {}, G: {}}
        self._init_real_time = monotonic()
        self._wall_time = time()
        self._init_proc_time = process_time()
        self._set_clocks()
        self.safe = safe
        if stub:
            self._stub = stub
            return
        self._server = AppMetricsServer(app_metrics=self, port=port, local_only=local_only, safe=safe)

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

    def close(self) -> None:
        self._server._close()

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

    def index_html(self) -> str:
        kz = self.metrics._stats.keys()

        lines = [
            "<html> <body> <tt>",
            '<table id="mtx" border="1" cellpadding="2"><h2>Application Metrics</h2></td>',
        ]

        for k in self.metrics._stats:
            tr = f'<tr><td colspan="2" id="{k}"><b>{k.upper()}</b></tr></td>'
            lines.append(tr)
            for m in self.metrics._stats[k]:
                n = m
                if m == "wall":
                    n = "current time"
                elif m == "real":
                    n = "process running time (s)"
                elif m == "proc":
                    n = "process cpu time (s)"
                tr = f'<tr><td>{n}</td><td><output id="{k}_{m}">*</output></td></tr>'
                lines.append(tr)

        lines.append("</table>\n</tt>\n")

        js = """
        <script type="text/javascript" id="metricsloader">
            function fetchMetricsData() {
                var httpRequest = new XMLHttpRequest();
                httpRequest.addEventListener("readystatechange", (url) => {
                    if (httpRequest.readyState === 4 && httpRequest.status === 200) {
                        var metricsInfo = JSON.parse(httpRequest.responseText);
                        for (const [section, sec_data] of Object.entries(metricsInfo)) {
                            for ([k, v] of Object.entries(sec_data)) {
                                var element_id = section + "_" + k;
                                if (element_id == "process_wall") {
                                    v = new Date(v*1000);
                                }
                                document.getElementById(element_id).innerText = v;
                            }
                        }
                    }
                });
                httpRequest.open("GET", "/data", true);
                httpRequest.send();
            }
            var metricsUpdateInterval = 2500; // millseconds
            var metricsTimer = setInterval(fetchMetricsData, metricsUpdateInterval);
            fetchMetricsData();
        </script>
        </body>
        </html>
        """

        return "\n".join(lines) + js

    def do_GET(self) -> None:
        shutdown: bool = False
        rcode = HTTPStatus.BAD_REQUEST  # assume something is amiss unless we prove otherwise
        content: str = '{"error": "bad request"}'
        content_type: str = "application/json"
        qqq: str = "/quitquitquit"
        # Each of the conditions is responsible for setting rcode, and filling `content`
        if False:  # just for the formatting
            pass
        elif self.path == "/":  # root page
            rcode = HTTPStatus.OK
            content_type = "text/html"
            content = self.index_html()
        elif self.path == "/data":  # data endpoint
            rcode = HTTPStatus.OK
            content = jdumps(self.metrics.get_stats(), indent=1)
        elif self.path.startswith(qqq):  # Exit handling logic
            pid = self.metrics._stats[P]["pid"]
            # in unsafe mode: only "/quitquitquit" is allowed
            # in safe mode: "/quitquitquit?<pid>" is required
            if (self.metrics.safe is False and self.path == qqq) or (
                (self.metrics.safe is True and self.path == f"{qqq}?{pid}")
            ):
                shutdown = True
                rcode = HTTPStatus.OK

                self.metrics._stats[P]["shutdown"] = True
                content = jdumps(self.metrics.get_stats(), indent=1)
            else:
                # copy the statistics so as not to mess with the storage structure
                errmsg = self.metrics._stats[P].copy()
                errmsg["httpstatus"] = rcode
                errmsg["error"] = f"invalid shutdown command; missing or extra PID arg"
                content = jdumps(errmsg, indent=1)
        else:  # anything else, use the default error message
            pass

        self.send_response(rcode)
        resp = content.encode() + b"\r\n"
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)
        if self.wfile.closed is False:
            self.wfile.flush()

        if shutdown:
            killpg(getpgrp(), SIGHUP)

    def log_message(self, format: str, *args: Any) -> None:
        "Intentional log suppression"
        pass


class AppMetricsServer:
    def __init__(
        self, app_metrics: AppMetrics, port: int = 8274, local_only: bool = True, appname: str = "", safe: bool = True
    ):
        address = "localhost" if local_only else "0.0.0.0"
        self._server_thread: Optional[Thread] = Thread(
            # deepcode ignore MissingAPI: Thread is joined below..
            target=self._make_http_thread,
            args=((address, port), app_metrics),
            daemon=True,
            name="varz_server",
        )
        self._server: Optional[HTTPServer] = None
        self.port = port
        self._server_thread.start()

    def __del__(self) -> None:
        self._close()

    def _make_http_thread(self, server_address, metrics: AppMetrics) -> None:
        AppMetricsReqHandler = partial(AppMetricsBaseReqHandler, metrics)
        self._server = HTTPServer(server_address=server_address, RequestHandlerClass=AppMetricsReqHandler)

        self.port = self._server.server_address[1]
        print(
            f"Started AppMetrics server on {self._server.server_address}",
            file=sys.stderr,
        )
        self._server.serve_forever()

    def _close(self) -> None:
        if self._server and isinstance(self._server, HTTPServer):
            self._server.shutdown()
            self._server.server_close()
            self._server = None

        if self._server_thread and isinstance(self._server_thread, Thread):
            self._server_thread.join(1)
            if self._server_thread.is_alive() is False:
                self._server_thread = None
