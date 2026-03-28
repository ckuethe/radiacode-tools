#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

from datetime import datetime
from io import StringIO
from os.path import dirname
from os.path import join as pathjoin

import pytest

from radiacode_tools.rc_files import _RCTRK_DEFAULT_NO_SERIAL_NUMBER, RcTrack
from radiacode_tools.rc_types import RcJSONEncoder
from radiacode_tools.rc_utils import BEGINNING_OF_TIME, UTC

testdir = pathjoin(dirname(__file__), "data")

testfile = pathjoin(testdir, "walk.rctrk")

def test_rctrk(monkeypatch):
    tk = RcTrack()
    tk.add_point(dt=BEGINNING_OF_TIME, latitude=0.0, longitude=0.0, accuracy=1.0, dose_rate=1.0, count_rate=1.0)
    assert str(tk)

    mock_ofd = StringIO()
    monkeypatch.setattr("builtins.open", lambda _filename, _mode: mock_ofd)
    monkeypatch.setattr(mock_ofd, "close", lambda: True)
    tk.write_file("/dev/stdout")

    # check that output looks vaguely reasonable
    generated_track = mock_ofd.getvalue().splitlines()
    assert len(generated_track) == 3, "two header lines and one data point"
    assert len(generated_track[-1].split("\t")) == 8, "there are 8 tab-delimited fields"


def test_rctrk_dict_jsonify():
    tk1 = RcTrack(pathjoin(testdir, "walk.rctrk"))
    jt = RcJSONEncoder().encode(tk1)
    assert jt


def test_rctrk_dict_roundtrip():
    tk1 = RcTrack(pathjoin(testdir, "walk.rctrk"))
    tk2 = RcTrack()

    tk2.from_dict(tk1.as_dict())
    assert len(tk1.points) == len(tk2.points)
    assert tk1.points[0].dt == tk2.points[0].dt


def test_rctrk_file_roundtrip(monkeypatch):
    tk1 = RcTrack(pathjoin(testdir, "walk.rctrk"))

    mock_ofd = StringIO()
    monkeypatch.setattr("builtins.open", lambda _filename, _mode: mock_ofd)
    monkeypatch.setattr(mock_ofd, "close", lambda: True)
    tk1.write_file("/dev/stdout")
    generated_track = mock_ofd.getvalue()

    mock_ifd = StringIO(generated_track)
    monkeypatch.setattr("builtins.open", lambda _filename, _mode: mock_ifd)
    monkeypatch.setattr(mock_ifd, "close", lambda: True)
    tk2 = RcTrack()
    tk2.load_file("/dev/stdin")
    assert len(tk1.points) == len(tk2.points)


def test_rctrk_bogus():
    tk = RcTrack()
    with pytest.raises(ValueError):
        tk.from_dict(dict())

    with pytest.raises(ValueError, match="missing header"):
        tk = RcTrack(__file__)  # of course this script isn't a valid track


def test_rctrk_null(monkeypatch):
    tk = RcTrack()
    assert tk.timestamp >= BEGINNING_OF_TIME

    mock_ofd = StringIO()
    monkeypatch.setattr("builtins.open", lambda _filename, _mode: mock_ofd)
    monkeypatch.setattr(mock_ofd, "close", lambda: True)

    assert not tk.name  # Track name was unset
    tk.write_file("/dev/stdout")
    assert tk.name.startswith("Track")  # A default track name was generated when the track was written

    # check that output looks vaguely reasonable
    generated_track = mock_ofd.getvalue().splitlines()
    fields = generated_track[0].split("\t")
    assert fields[0].startswith("Track:")
    assert fields[0].endswith(tk.name)
    assert fields[1] == _RCTRK_DEFAULT_NO_SERIAL_NUMBER
    assert not fields[2]  # No comment
    assert fields[3] == "EC"

    assert len(generated_track[-1].split("\t")) == 8, "there are 8 tab-delimited fields"
    assert len(generated_track) == 2, "Header is valid, even if no measurements are present"


def test_rctrkadd_dict_and_timestamp():
    tk = RcTrack()
    test_year = 2025

    # reject adding offset-naive timestamp as the first point
    with pytest.raises(TypeError, match="offset-aware datetime"):
        tk.add_point_dict(
            {
                "DateTime": datetime(test_year, 1, 1, 0, 0, 0),
                "Latitude": 0.0,
                "Longitude": 0.0,
                "Accuracy": 1.0,
                "DoseRate": 1.0,
                "CountRate": 1.0,
            }
        )

    # this time with tzinfo
    tk.add_point_dict(
        {
            "DateTime": datetime(test_year, 1, 1, 0, 0, 0, tzinfo=UTC),
            "Latitude": 0.0,
            "Longitude": 0.0,
            "Accuracy": 1.0,
            "DoseRate": 1.0,
            "CountRate": 1.0,
        }
    )
    assert tk.timestamp.year == test_year

    # try add a second point, also without tzinfo
    with pytest.raises(TypeError, match="offset-aware datetime"):
        tk.add_point_dict(
            {
                "DateTime": datetime(test_year - 1, 1, 1, 0, 0, 0),
                "Latitude": 0.0,
                "Longitude": 0.0,
                "Accuracy": 1.0,
                "DoseRate": 1.0,
                "CountRate": 1.0,
            }
        )

    # add an old point with tzinfo, check that timestamp is correctly updated
    tk.add_point_dict(
        {
            "DateTime": BEGINNING_OF_TIME,
            "Latitude": 0.0,
            "Longitude": 0.0,
            "Accuracy": 1.0,
            "DoseRate": 1.0,
            "CountRate": 1.0,
        }
    )
    assert tk.timestamp == BEGINNING_OF_TIME

    # add a point after the oldest point, ensure that timestamp is preserved
    tk.add_point_dict(
        {
            "DateTime": BEGINNING_OF_TIME.replace(year=test_year - 1),
            "Latitude": 0.0,
            "Longitude": 0.0,
            "Accuracy": 1.0,
            "DoseRate": 1.0,
            "CountRate": 1.0,
        }
    )
    assert tk.timestamp == BEGINNING_OF_TIME


def test_rctrack_df_property():
    """Test that df property returns the internal DataFrame"""
    from radiacode_tools.rc_files import RcTrack
    import pandas as pd
    
    track = RcTrack(testfile)
    df = track.df
    
    assert isinstance(df, pd.DataFrame)
    assert len(df) == len(track.points)
    assert "DateTime" in df.columns
    assert "Latitude" in df.columns
    assert "Longitude" in df.columns


def test_rctrack_df_direct_modification():
    """Test direct DataFrame modification"""
    from radiacode_tools.rc_files import RcTrack
    import pandas as pd
    
    track = RcTrack(testfile)
    original_len = len(track.df)
    
    track.df.loc[len(track.df)] = {
        "DateTime": datetime(2023, 1, 1, tzinfo=UTC),
        "Latitude": 0,
        "Longitude": 0,
        "Accuracy": 10,
        "DoseRate": 0.1,
        "CountRate": 10,
        "Flags": "E"
    }
    
    assert len(track.df) == original_len + 1


def test_rctrack_filter_by_timerange():
    """Test filter_by_timerange method"""
    from radiacode_tools.rc_files import RcTrack
    
    track = RcTrack(testfile)
    original_len = len(track.df)
    
    if original_len > 0:
        first_dt = track.df.iloc[0]["DateTime"]
        last_dt = track.df.iloc[-1]["DateTime"]
        
        track.filter_by_timerange(first_dt, last_dt, inclusive_end=False)
        
        assert len(track.df) <= original_len


def test_rctrack_filter_by_timerange_inverse():
    """Test filter_by_timerange_inverse method"""
    from radiacode_tools.rc_files import RcTrack
    
    track = RcTrack(testfile)
    original_len = len(track.df)
    
    track.filter_by_timerange_inverse(datetime(2000, 1, 1, tzinfo=UTC), datetime(2001, 1, 1, tzinfo=UTC))
    
    assert len(track.df) == original_len


def test_rctrack_filter_by_geobox():
    """Test filter_by_geobox method"""
    from radiacode_tools.rc_files import RcTrack
    
    track = RcTrack(testfile)
    original_len = len(track.df)
    
    if original_len > 0:
        min_lat = track.df["Latitude"].min()
        max_lat = track.df["Latitude"].max()
        min_lon = track.df["Longitude"].min()
        max_lon = track.df["Longitude"].max()
        
        track.filter_by_geobox(min_lat, min_lon, max_lat, max_lon)
        
        assert len(track.df) <= original_len


def test_rctrack_filter_by_geobox_inverse():
    """Test filter_by_geobox_inverse method"""
    from radiacode_tools.rc_files import RcTrack
    
    track = RcTrack(testfile)
    original_len = len(track.df)
    
    track.filter_by_geobox_inverse(100, 100, 101, 101)
    
    assert len(track.df) == original_len


def test_rctrack_filter_by_geocircle():
    """Test filter_by_geocircle method"""
    from radiacode_tools.rc_files import RcTrack
    
    track = RcTrack(testfile)
    original_len = len(track.df)
    
    if original_len > 0:
        center_lat = track.df.iloc[0]["Latitude"]
        center_lon = track.df.iloc[0]["Longitude"]
        
        track.filter_by_geocircle(center_lat, center_lon, 1000000)
        
        assert len(track.df) <= original_len


def test_rctrack_filter_by_geocircle_inverse():
    """Test filter_by_geocircle_inverse method"""
    from radiacode_tools.rc_files import RcTrack
    
    track = RcTrack(testfile)
    original_len = len(track.df)
    
    track.filter_by_geocircle_inverse(100, 100, 1000)
    
    assert len(track.df) == original_len


def test_rctrack_points_property_new_list():
    """Test that points property returns a new list each time"""
    from radiacode_tools.rc_files import RcTrack
    
    track = RcTrack(testfile)
    
    points1 = track.points
    points2 = track.points
    
    assert points1 is not points2
    assert len(points1) == len(points2)
    assert points1 == points2


def test_rctrack_points_empty_track():
    """Test points property on empty track"""
    from radiacode_tools.rc_files import RcTrack
    
    track = RcTrack()
    
    points = track.points
    
    assert points == []
    assert isinstance(points, list)


def test_rctrack_points_contains_trackpoint():
    """Test that points contain TrackPoint objects"""
    from radiacode_tools.rc_files import RcTrack
    from radiacode_tools.rc_types import TrackPoint
    
    track = RcTrack(testfile)
    
    points = track.points
    
    if len(points) > 0:
        assert isinstance(points[0], TrackPoint)


def test_rctrack_add_point_dataframe_growth():
    """Test that add_point properly grows the DataFrame"""
    from radiacode_tools.rc_files import RcTrack
    from datetime import datetime
    
    track = RcTrack()
    initial_len = len(track.df)
    
    track.add_point(
        dt=datetime(2023, 1, 1, tzinfo=UTC),
        latitude=1.0,
        longitude=2.0,
        accuracy=5,
        dose_rate=0.1,
        count_rate=10
    )
    
    assert len(track.df) == initial_len + 1


def test_rctrack_empty_track_properties():
    """Test properties on empty track"""
    from radiacode_tools.rc_files import RcTrack
    
    track = RcTrack()
    
    assert len(track.df) == 0
    assert track.points == []
    assert track.name == ""
    assert track.serialnumber == "Unknown Device"
    assert track.comment == ""


def test_rctrack_name_serial_comment_properties():
    """Test name, serialnumber, and comment properties"""
    from radiacode_tools.rc_files import RcTrack
    
    track = RcTrack()
    
    track.name = "test_name"
    track.serialnumber = "RC-100-123456"
    track.comment = "test_comment"
    
    assert track.name == "test_name"
    assert track.serialnumber == "RC-100-123456"
    assert track.comment == "test_comment"


def test_rctrack_multiple_points_order():
    """Test that multiple points are stored in correct order"""
    from radiacode_tools.rc_files import RcTrack
    from datetime import datetime
    
    track = RcTrack()
    
    track.add_point(dt=datetime(2023, 1, 1, tzinfo=UTC), latitude=1, longitude=1, accuracy=5, dose_rate=0.1, count_rate=10)
    track.add_point(dt=datetime(2023, 1, 2, tzinfo=UTC), latitude=2, longitude=2, accuracy=5, dose_rate=0.2, count_rate=20)
    track.add_point(dt=datetime(2023, 1, 3, tzinfo=UTC), latitude=3, longitude=3, accuracy=5, dose_rate=0.3, count_rate=30)
    
    assert len(track.df) == 3
    assert track.df.iloc[0]["Latitude"] == 1
    assert track.df.iloc[1]["Latitude"] == 2
    assert track.df.iloc[2]["Latitude"] == 3


def test_rctrack_df_columns():
    """Test that DataFrame has expected columns"""
    from radiacode_tools.rc_files import RcTrack
    
    track = RcTrack(testfile)
    
    expected_columns = {"DateTime", "Latitude", "Longitude", "Accuracy", "DoseRate", "CountRate", "Comment"}
    actual_columns = set(track.df.columns)
    
    assert expected_columns.issubset(actual_columns)
