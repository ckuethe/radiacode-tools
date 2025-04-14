#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

from time import sleep

import pytest
import requests

from radiacode_tools import appmetrics

name: str = "appmetrics_test"


@pytest.mark.slow
def test_stub():
    amx = appmetrics.AppMetrics(stub=True, appname=name)

    d = amx.get_stats()
    assert d["process"]["appname"] == name
    assert d["process"]["pid"] > 0

    cv = 42
    cn = "a"
    amx.counter_create(cn, cv)
    assert d["counter"][cn] == cv
    amx.counter_increment(cn)
    assert d["counter"][cn] == cv + 1

    gn = "b"
    gv = 13
    amx.gauge_create(gn)
    assert d["gauge"][gn] == 0
    amx.gauge_update(gn, gv)
    assert d["gauge"][gn] == gv

    fn = "c"
    amx.flag_create(fn)
    assert d["flag"][fn] is False
    amx.flag_set(fn)
    assert d["flag"][fn] is True
    amx.flag_clear(fn)
    assert d["flag"][fn] is False

    sleep(0.1)
    b = amx.get_stats()
    assert d["process"]["pid"] == b["process"]["pid"]


def test_errors():
    name = "foobar"
    amx = appmetrics.AppMetrics(stub=True, appname=name)

    cn = "a"
    amx.counter_create(cn)
    with pytest.raises(ValueError):  # already exists
        amx.counter_create(cn)
    with pytest.raises(KeyError):  # doesn't exist
        amx.counter_decrement("x")

    gn = "b"
    amx.gauge_create(gn)
    with pytest.raises(ValueError):  # already exists
        amx.gauge_create(gn)
    with pytest.raises(KeyError):  # doesn't exist
        amx.gauge_update("x", 0)

    fn = "c"
    amx.flag_create(fn)
    with pytest.raises(ValueError):  # already exists
        amx.flag_create(fn)
    with pytest.raises(KeyError):  # doesn't exist
        amx.flag_setval("x", True)

    with pytest.raises(ValueError):
        amx._create_metric("invalid", "foo", None)


@pytest.mark.slow
def test_server():
    amx = appmetrics.AppMetrics(appname=name, port=0)  # 0 = random port
    n = 20
    while True:
        assert n > 0, "Timed out waiting for server to start"
        sleep(0.05)
        if amx._server.port:
            break

    srv = f"http://127.0.0.1:{amx._server.port}"

    # HTML index page
    resp = requests.get(f"{srv}/")
    assert resp.ok
    assert resp.headers["Content-Type"] == "text/html"
    assert "Application Metrics" in resp.text

    # data
    resp = requests.get(f"{srv}/data")
    assert resp.ok
    d = resp.json()
    assert resp.headers["Content-Type"] == "application/json"
    assert d["process"]["appname"] == name
    assert d["process"]["pid"]
    assert d["process"]["real"]
    assert d["process"]["wall"]

    # anything else should also return valid json, though it's not a valid request
    resp = requests.get(f"{srv}/fail")
    assert resp.ok is False
    assert resp.json()

    # shutdown command in safe mode requires the PID
    resp = requests.get(f"{srv}/quitquitquit")
    assert resp.ok is False
    assert resp.status_code == appmetrics.HTTPStatus.BAD_REQUEST
    assert "invalid shutdown command" in resp.text

    assert amx.close() is None
