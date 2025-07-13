#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import datetime

import pytest

from radiacode_tools import rc_radqr

qr_tests = [
    (
        # From the raddata spec
        (
            "RADDATA://G0/000/NCFI%20UHKEK41II6W%25M%2F96V769L6GUAM1NTSQZT6%20T6%2576MD6HTM%25%2BMJ%2566"
            "GA30N8-5E9Q6%2FPB8EP%201J41PF6376%3AQ6RF6R11%3AQ6PF6IX6ABETF6B9RGL6*O64JQ5H10GJVBJ385WEB6P5"
            "HPB%3A1JH4TZ%2BSLA5Y6TLXK7*K-4JZO0%2B%3AUHH6TNOVJ5A-PDYR3FWZXHPZHLXHV53%2B43RP63M0VS35.7D.L"
            "DPFM0A23O7%2FV%25AFILUMVSP5P.%20H%3A835G0HP56PPE.C.XPCSH26046U0-R.EN%2BCE2OCNNCLSK*RKGJ4N%2"
            "0S1BNX1G%24%20B-%2BE%25JOTPDB%3AD2H6QMB4%2BQ57QWSQF%2BRK3N%241I73KAABXGRBT35%24I7GLCIQFS49%"
            "2BR2JV%20GOK%24JN%24OYDTY49S6D546M2BM1CG6DE10N131AC146K3GP1DHNBA5L%201A%2B.5D7OZ39P8E704K9E"
            "R%3A84DRZJUVFM%2F%24K421%2B3GL28W69JMAWPE*M6GI1QL8M%25FPK65X9AW3-I07X7Q%20DXI22Y9IU3.W1NDGH"
            "XJ.0R%2FTIB3A%3AB9%2576K4JJ%242M%20SBSCKJSPI20EA5Y6%3AQUY%25HYQHP%25PNL1%2F%2F6UCA7.SW5TLPC"
            "%20%20C7VCZ%20C-RSWJCGPCZJCG8C6C0*Z2*70PF6746FH60DB%3AN1ZZ16M4*BQXO1-48L48E%2041DK654QEHXT8"
            "%3A12*Q8JBIJPCEES%3AM6ITBD9I2DPP%251B%255Q%200AAK%2BM2TP47%240XCB%25DF*AHT.9VWJ1M4%20O49PENJF"
        ),
        {
            "specver": 0,
            "options": 0,
            "n_uris": 0,
            "n_spectra": 0,
            "deflated": True,
            "base_x_encoded": True,
            "use_base64": False,
            "csv_channel_data": False,
            "rle_zero_compress": True,
            "type": "F",
            "meas_time": [299.0, 300.01],
            "energy_calibration": [2.929687, 5.859374],
            "model": "Kromek D3S",
            "timestamp": datetime.datetime(2019, 12, 10, 11, 22, 55),
            "location": [37.6765, -121.7068],
            "neutrons": 7,
            "comment": "Item of interest",
            "channels": 512,
            "counts": (
                # represented here as a string for readability
                "0, 0, 0, 0, 0, 0, 172, 255, 307, 358, 365, 436, 394, 423, 399, 399, 412, 398, 437,"
                "445, 456, 492, 507, 478, 482, 464, 477, 479, 457, 436, 422, 437, 419, 429, 442, 416,"
                "416, 440, 433, 446, 400, 361, 364, 315, 294, 260, 243, 237, 246, 249, 221, 163, 213,"
                "189, 193, 170, 173, 169, 177, 148, 149, 150, 135, 149, 134, 137, 123, 117, 134, 109,"
                "122, 134, 120, 136, 102, 140, 113, 93, 73, 93, 96, 108, 77, 100, 91, 90, 103, 85, 83,"
                "98, 76, 109, 98, 95, 84, 81, 105, 108, 83, 97, 87, 67, 85, 89, 64, 67, 79, 86, 74,"
                "69, 55, 77, 74, 67, 55, 80, 62, 68, 79, 83, 74, 86, 58, 79, 58, 67, 60, 61, 76, 66,"
                "88, 73, 59, 74, 68, 78, 82, 65, 61, 87, 78, 76, 58, 87, 67, 65, 76, 69, 83, 87, 89,"
                "86, 89, 98, 83, 88, 65, 79, 78, 78, 70, 89, 77, 53, 56, 55, 49, 54, 63, 56, 50, 49,"
                "52, 47, 59, 54, 52, 41, 48, 44, 35, 48, 53, 46, 54, 43, 49, 52, 44, 41, 42, 44, 52,"
                "40, 54, 80, 87, 108, 148, 123, 141, 146, 151, 145, 124, 97, 96, 55, 47, 30, 19, 19, 6,"
                "11, 14, 6, 8, 15, 14, 21, 20, 32, 29, 53, 66, 73, 85, 92, 102, 93, 113, 104, 94, 84,"
                "63, 48, 52, 33, 33, 13, 11, 11, 6, 3, 5, 1, 1, 3, 5, 6, 2, 9, 2, 6, 6, 4, 2, 3, 0, 2,"
                "0, 2, 4, 2, 0, 3, 0, 2, 1, 0, 0, 1, 1, 1, 3, 0, 2, 2, 0, 0, 1, 0, 0, 3, 1, 2, 1, 1, 1,"
                "0, 0, 0, 1, 0, 0, 0, 1, 2, 0, 1, 0, 0, 2, 0, 0, 0, 0, 0, 1, 1, 0, 1, 2, 2, 1, 0, 1, 0,"
                "1, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0,"
                "1, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0, 0,"
                "0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 2, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0,"
                "2, 0, 0, 0, 1, 0, 0, 0, 2, 0, 2, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 1, 0, 0, 0, 1,"
                "0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,"
                "0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0,"
                "0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0"
            ),
        },
    ),
]


def test_radqr_decode():
    for x in qr_tests:
        fields = rc_radqr.decode_qr_data(x[0], debug=True)
        x[1]["counts"] = [int(i) for i in x[1]["counts"].split(",")]
        assert fields == x[1]


def test_radqr_decode_alt_scheme():
    for x in qr_tests:
        # Scheme is should be case-insensitive
        msg = x[0].replace("RADDATA", "raddata")
        fields = rc_radqr.decode_qr_data(msg)
        assert fields["model"] == x[1]["model"]

        # "interspec" and "raddata" are both valid schemes
        msg = x[0].replace("RADDATA", "interspec")
        fields = rc_radqr.decode_qr_data(msg)
        assert fields["model"] == x[1]["model"]


def test_radqr_decode_fail():
    # Check URI schem
    with pytest.raises(ValueError):
        msg = qr_tests[0][0].replace("RADDATA", "http")
        _ = rc_radqr.decode_qr_data(msg)
    with pytest.raises(ValueError):
        msg = qr_tests[0][0].replace("RADDATA", "Xraddata")
        _ = rc_radqr.decode_qr_data(msg)
    with pytest.raises(ValueError):
        msg = qr_tests[0][0].replace("RADDATA", "interspecX")
        _ = rc_radqr.decode_qr_data(msg)

    # Check URI version
    with pytest.raises(ValueError, match="Unsupported Version") as cm:
        msg = qr_tests[0][0].replace("/G0/", "/G1/")
        _ = rc_radqr.decode_qr_data(msg)

    # Check Flags - most of these will throw AttributeError when the regex doesn't match
    with pytest.raises(ValueError):
        msg = qr_tests[0][0].replace("/000/", "//")  # can't be empty
        _ = rc_radqr.decode_qr_data(msg)
    with pytest.raises(ValueError):
        msg = qr_tests[0][0].replace("/000/", "/00/")  # less than 3 characters is too short
        _ = rc_radqr.decode_qr_data(msg)
    with pytest.raises(ValueError):
        msg = qr_tests[0][0].replace("/000/", "/00000/")  # more than 4 characters is too long
        _ = rc_radqr.decode_qr_data(msg)
    with pytest.raises(ValueError):
        msg = qr_tests[0][0].replace("/000/", "/X000/")  # Only hexchars [0-9a-f]
        _ = rc_radqr.decode_qr_data(msg)
    with pytest.raises(ValueError, match="Undefined option bits set") as cm:
        msg = qr_tests[0][0].replace("/000/", "/ffff/")  # undefined flags
        _ = rc_radqr.decode_qr_data(msg)


def test_radqr_encode_fail_bad_times():
    with pytest.raises(ValueError, match="live time cannot be greater than real time") as cm:
        rc_radqr.make_qr_payload(lr_times=(1, 0), spectrum=[0])


def test_radqr_encode_minimum():
    result = rc_radqr.make_qr_payload(lr_times=(0, 0), spectrum=[0], options=rc_radqr.OPT_CSV_SPECTRUM)
    # my encoder won't use  CountedZeros compression ("RLE0") if it doesn't save space. It will
    # signal this by setting the NO_SPEC_RLE0 option in the return value
    assert result[0] == rc_radqr.OPT_CSV_SPECTRUM | rc_radqr.OPT_NO_SPEC_RLE0
    assert result[1] == b"T:0,0 S:0"


def test_radqr_encode_tiny():
    # bigger payload, 1024 channels ... all zero
    options = rc_radqr.OPT_CSV_SPECTRUM | rc_radqr.OPT_NO_DEFLATE | rc_radqr.OPT_NO_BASE_X
    result = rc_radqr.make_qr_payload(
        lr_times=(0, 0),
        spectrum=[0] * 1024,
        comments="no comment",
        detector_model="RC-102",
        options=options,
    )
    assert result[0] == options
    assert b"T:0,0 S:0,1024" in result[1]


def test_radqr_encode_fail():
    lr_times = (0, 0)
    spectrum = [0] * 256
    with pytest.raises(ValueError):
        rc_radqr.make_qr_payload(lr_times=[1], spectrum=spectrum)
    with pytest.raises(ValueError):
        rc_radqr.make_qr_payload(lr_times=lr_times, spectrum=spectrum, mclass="?")
    with pytest.raises(ValueError):
        rc_radqr.make_qr_payload(lr_times=lr_times, spectrum=spectrum, neutron_count=-1)
    with pytest.raises(ValueError):
        rc_radqr.make_qr_payload(lr_times=lr_times, spectrum=spectrum, deviations=[(0, 0), (1,)])
    with pytest.raises(ValueError):
        rc_radqr.make_qr_payload(lr_times=lr_times, spectrum=spectrum, deviations="foo")
    with pytest.raises(ValueError):
        rc_radqr.make_qr_payload(lr_times=lr_times, spectrum=spectrum, location=[0])


def test_radqr_encode_full():
    # bigger payload, 1024 channels ... all zero
    comments = "Thank goodness it's not the demon core"
    detector_model = "RadiaCode RC-102"
    timestamp = datetime.datetime(1945, 7, 15, 11, 29, 21)
    tstr = timestamp.strftime("%Y%m%dT%H%M%S")

    result = rc_radqr.make_qr_payload(
        lr_times=(0, 0),
        spectrum=[0] * 1024,
        calibration=[1, 2, 3],
        deviations=[(0, 0), (511, 0), (1461, 0)],
        mclass="F",
        detector_model=detector_model,
        neutron_count=3141592653,
        location=(33.6772929, -106.477862),
        comments=comments,
        timestamp=timestamp,
    )
    assert result[0] == 0
    assert comments.encode() in result[1]
    assert detector_model.encode() in result[1]
    assert tstr.encode() in result[1]

    decoded = rc_radqr.parse_payload_fields(result[1])
    assert decoded["model"] == detector_model


def test_radqr_decode_invalid_field():
    # check that invalid fields are rejected
    with pytest.raises(ValueError, match="Unknown field: Z") as cm:
        rc_radqr.parse_payload_fields(b"T:0,0 Z:INVALID S:0")
