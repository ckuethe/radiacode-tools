#!/usr/bin/env python3
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

from datetime import datetime
from os.path import dirname
from os.path import join as pathjoin

import pytest

testdir = pathjoin(dirname(__file__), "data")
testfile = pathjoin(testdir, "walk.rctrk")

from radiacode_tools.rc_files import RcTrack
from radiacode_tools.rc_types import GeoBox, GeoCircle, GeoPoint, TimeRange
from track_edit import (
    check_geoboxes,
    check_geocircles,
    check_timeranges,
    earthdistance,
    edit_track,
    get_args,
    main,
)


def test_argparse_no_args(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__])
    with pytest.raises(SystemExit):
        get_args()


def test_argparse_filename(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, testfile])
    a = get_args()
    assert testfile == a.filename


def test_earthdistance1():
    # haversine assumes spherical earth. The circumference of the earth is about
    # 40075km around the equator, and 40007km through the poles. Let's average those
    # and take half that distance to estimate the distance between antipodes to be
    # about 20020km
    d_a = 20020
    tol = 10  # good enough for this approximation
    d_e = earthdistance(0, 0, 0, 180) / 1000
    d_p = earthdistance(-90, 0, 90, 0) / 1000
    assert d_e == d_p  # this should be true assuming a spherical earth
    assert pytest.approx(d_a, abs=tol) == d_e


def test_earthdistance2():
    JFK = (40.7033448, -73.8919609)
    LAX = (33.9655136, -118.4181808)
    LHR = (51.4700628, -0.4559553)
    NRT = (35.7734217, 140.3875152)
    SFO = (37.6294499, -122.3582975)
    SYD = (-33.8766012, 151.1437224)
    tol = 10
    d_jfk_lon = earthdistance(*JFK, *LHR) / 1000
    d_lax_nrt = earthdistance(*LAX, *NRT) / 1000
    d_sfo_syd = earthdistance(*SFO, *SYD) / 1000
    # Distances computed using the calculator at https://www.nhc.noaa.gov/gccalc.shtml
    assert pytest.approx(d_jfk_lon, abs=tol) == 5539
    assert pytest.approx(d_lax_nrt, abs=tol) == 8745
    assert pytest.approx(d_sfo_syd, abs=tol) == 11942


def test_edit_main(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, "-o", "/dev/null", testfile])
    assert main() is None


def test_edit_track_noop(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, testfile])
    args = get_args()
    track = RcTrack(args.filename)
    a, b = edit_track(args, track)
    assert a == b
    assert b > 0


def test_edit_track_exclude_timerange_all(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, "-n", "exclude_timerange_test", "-T", "~", testfile])
    args = get_args()
    track = RcTrack(args.filename)
    a, b = edit_track(args, track)
    assert 0 == b


def test_edit_track_exclude_timerange_none(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, "-n", "exclude_timerange_test", "-T", "~2000-01-01T00:00:00Z", testfile])
    args = get_args()
    track = RcTrack(args.filename)
    a, b = edit_track(args, track)
    assert a == b


def test_edit_track_include_timerange_all(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, "-n", "include_timerange_test", "-t", "~", testfile])
    args = get_args()
    track = RcTrack(args.filename)
    a, b = edit_track(args, track)
    assert a == b


def test_edit_track_include_timerange_none(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, "-n", "include_timerange_test", "-t", "~2000-01-01T00:00:00Z", testfile])
    args = get_args()
    track = RcTrack(args.filename)
    a, b = edit_track(args, track)
    assert 0 == b


def test_edit_track_include_geocircle_all(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, "-n", "include_geocircle_test", "-r", "0,0,1000", testfile])
    args = get_args()
    track = RcTrack(args.filename)
    a, b = edit_track(args, track)
    assert a == b


def test_edit_track_include_geocircle_none(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, "-n", "include_geocircle_test", "-r", "1,1,1000", testfile])
    args = get_args()
    track = RcTrack(args.filename)
    a, b = edit_track(args, track)
    assert 0 == b


def test_edit_track_exclude_geocircle_all(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, "-n", "exclude_geocircle_test", "-R", "0,0,1000", testfile])
    args = get_args()
    track = RcTrack(args.filename)
    a, b = edit_track(args, track)
    assert 0 == b


def test_edit_track_exclude_geocircle_none(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, "-n", "exclude_geocircle_test", "-R", "1,1,1000", testfile])
    args = get_args()
    track = RcTrack(args.filename)
    a, b = edit_track(args, track)
    assert a == b


def test_edit_track_include_geobox_all(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, "-n", "include_geobox_test", "-g", "0,0~1,1", testfile])
    args = get_args()
    track = RcTrack(args.filename)
    a, b = edit_track(args, track)
    assert a == b


def test_edit_track_include_geobox_none(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, "-n", "include_geobox_test", "-g", "1,1~2,2", testfile])
    args = get_args()
    track = RcTrack(args.filename)
    a, b = edit_track(args, track)
    assert 0 == b


def test_edit_track_exclude_geobox_all(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, "-n", "exclude_geobox_test", "-G", "0,0~1,1", testfile])
    args = get_args()
    track = RcTrack(args.filename)
    a, b = edit_track(args, track)
    assert 0 == b


def test_edit_track_exclude_geobox_none(monkeypatch):
    monkeypatch.setattr("sys.argv", [__file__, "-n", "exclude_geobox_test", "-G", "1,1~2,2", testfile])
    args = get_args()
    track = RcTrack(args.filename)
    a, b = edit_track(args, track)
    assert a == b


def test_check_timeranges_dataframe():
    """Test check_timeranges with DataFrame input"""
    import pandas as pd

    df = pd.DataFrame({"DateTime": [datetime(2023, 1, 1), datetime(2023, 1, 2), datetime(2023, 1, 3)]})

    tr1 = TimeRange(dt_start=datetime(2023, 1, 1), dt_end=datetime(2023, 1, 2))
    tr2 = TimeRange(dt_start=datetime(2023, 1, 2), dt_end=datetime(2023, 1, 3))

    result = check_timeranges(df, [tr1, tr2])
    assert len(result) == 3
    assert result.iloc[0] == True
    assert result.iloc[1] == True
    assert result.iloc[2] == False


def test_check_geoboxes_dataframe():
    """Test check_geoboxes with DataFrame input"""
    import pandas as pd

    df = pd.DataFrame({"Latitude": [0, 0.5, 2], "Longitude": [0, 0.5, 2]})

    p1 = GeoPoint(latitude=0, longitude=0)
    p2 = GeoPoint(latitude=1, longitude=1)
    gb = GeoBox(p1=p1, p2=p2)

    result = check_geoboxes(df, [gb])
    assert len(result) == 3
    assert result.iloc[0] == True
    assert result.iloc[1] == True
    assert result.iloc[2] == False


def test_check_geocircles_dataframe():
    """Test check_geocircles with DataFrame input"""
    import pandas as pd

    df = pd.DataFrame({"Latitude": [0, 10, 20], "Longitude": [0, 10, 20]})

    center = GeoPoint(latitude=0, longitude=0)
    gc = GeoCircle(point=center, radius=1000000)

    result = check_geocircles(df, [gc])
    assert len(result) == 3
    assert result.iloc[0] == True
    assert result.iloc[1] == False
    assert result.iloc[2] == False


def test_edit_track_include_exclude_combined():
    """Test edit_track with both include and exclude filters"""
    from argparse import Namespace

    from radiacode_tools.rc_files import RcTrack
    from track_edit import edit_track

    track = RcTrack(testfile)
    before_len = len(track.df)

    args = Namespace(
        include_time_range=[],
        exclude_time_range=[],
        include_geo=[],
        exclude_geo=[],
        include_radius=[],
        exclude_radius=[],
        track_name="combined_test",
        output="/dev/null",
        filename=testfile,
    )

    a, b = edit_track(args, track)
    assert a == b
    assert b > 0
