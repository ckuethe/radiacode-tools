#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

from time import sleep

import pytest

from radiacode_tools import appmetrics


@pytest.mark.slow
def test_stub():
    name = "foobar"
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
