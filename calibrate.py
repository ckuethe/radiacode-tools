#!/usr/bin/env python
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

from argparse import ArgumentParser, Namespace
from numpy import corrcoef
from numpy.polynomial import Polynomial
from tempfile import mkstemp
import os
from typing import NoReturn, List, Tuple, Union, Iterable
import json
from sys import exit

Numeric = Union[int, float]


def template_calibration(args: Namespace) -> NoReturn:
    # RC-102 is roughly 2.8 keV per channel. This is a sample calibration;
    # measure some with your own device and fill in the appropriate channel
    # numbers.
    blob = """{
  "unobtainium": "Remove this line after filling in actual calibration measurements. The channel mapping below is a rough (aka. wrong) linear model...",
  "americium": [
    { "energy": 26, "channel": 9 },
    { "energy": 60, "channel": 21 }
  ],
  "barium": [
    { "energy": 80, "channel": 28 },
    { "energy": 166, "channel": 59 },
    { "energy": 303, "channel": 109 },
    { "energy": 356, "channel": 128 }
  ],
  "europium": [
    { "energy": 40, "channel": 14 },
    { "energy": 122, "channel": 44 },
    { "energy": 245, "channel": 88 },
    { "energy": 344, "channel": 124 },
    { "energy": 1098, "channel": 395 },
    { "energy": 1408, "channel": 507 }
  ],
  "potassium": [
    { "energy": 1461, "channel": 526 }
  ],
  "radium": [
    { "energy": 295, "channel": 106 },
    { "energy": 352, "channel": 126 },
    { "energy": 609, "channel": 219 },
    { "energy": 1120, "channel": 403 },
    { "energy": 1765, "channel": 635 },
    { "energy": 2204, "channel": 793 }
  ],
  "sodium": [
    { "energy": 511, "channel": 184 },
    { "energy": 1275, "channel": 459 }
  ],
  "thorium": [
    { "energy": 338, "channel": 121 },
    { "energy": 583, "channel": 210 },
    { "energy": 911, "channel": 328 },
    { "energy": 1588, "channel": 572 },
    { "energy": 2614, "channel": 941 }
  ]
}
    """

    if os.path.exists(args.cal_file):
        print(f"Output file '{args.cal_file}' already exists")
    tfd, tfn = mkstemp()
    os.close(tfd)
    with open(tfn, "w") as ofd:
        ofd.write(blob)
    os.rename(tfn, args.cal_file)

    exit(0)


def load_calibration(args: Namespace) -> List[Tuple[Numeric, Numeric]]:
    """
    Calibration file is a json file which contains a dict like this:

    {
        "element1" : [
            {"channel": <number>, "energy": <number>},
            ...
            {"channel": <number>, "energy": <number>}
            ],
        ...
        "elementN" : [
            {"channel": <number>, "energy": <number>},
            ...
            {"channel": <number>, "energy": <number>}
            ],
    }

    """
    rv = []
    with open(args.cal_file) as ifd:
        data = json.load(ifd)
    for element in data:
        for cal_point in data[element]:
            rv.append((cal_point["channel"], cal_point["energy"]))

    rv.sort(key=lambda x: x[0])
    # It may help the polynomial fit to force a 0/0 data point.
    if args.zero_start and rv[0] != (0, 0):
        rv.insert(0, (0, 0))
    return rv


def get_args() -> Namespace:
    def _positive_int(s) -> int:
        f = float(s)
        i = int(s)
        if f < 1:
            # catch non-numeric
            raise ValueError
        if f - i != 0:
            # catch fractional part != 0
            raise ValueError
        return i

    ap = ArgumentParser()
    ap.add_argument(
        "-z",
        "--zero-start",
        default=False,
        action="store_true",
        help="Add a synthetic (0,0) calibration data point",
    )
    ap.add_argument(
        "-f",
        "--cal-file",
        type=str,
        default="radiacode.json",
        metavar="FILE",
        help="Calibration data file [%(default)s]",
    )
    ap.add_argument(
        "-o",
        "--order",
        type=_positive_int,
        default=2,
        metavar="N",
        help="Calibration polynomial order [%(default)d]",
    )
    ap.add_argument(
        "-p",
        "--precision",
        type=_positive_int,
        default=8,
        metavar="N",
        help="Number of decimal places in calibration factors [%(default)d]",
    )
    ap.add_argument(
        "-W",
        "--write-template",
        default=False,
        action="store_true",
        help="Generate a template calibration file",
    )
    return ap.parse_args()


def rsquared(
    xlist: Iterable[Numeric], ylist: Iterable[Numeric], coeffs: Iterable[Numeric]
) -> float:
    """
    Compute R^2 for the fit model

    xlist: an array of x-axis values
    ylist: an array of y-value measurements of the same dimension as xlist
    coeffs: an iterable of polynomial coefficients, least significant first (x^0, x^1, .. , x^n)
    """
    chan2kev = Polynomial(coeffs)
    computed: List[Numeric] = [chan2kev(i) for i in xlist]
    corr_matrix = corrcoef(ylist, computed)
    r_squared = corr_matrix[0, 1] ** 2

    print(f"R^2: {r_squared:.5f}")
    return r_squared


def main() -> None:
    args = get_args()

    if args.write_template:
        template_calibration(args)

    try:
        data = load_calibration(args)
    except FileNotFoundError:
        print(f"Calibration file '{args.cal_file}' does not exist")
        exit(1)
    except TypeError:
        print(f"Data format error loading calibration file")
        exit(1)
    chan, energy = zip(*data)

    print(f"data range: {data[0]} - {data[-1]}")

    pf = Polynomial.fit(
        chan, energy, deg=args.order, window=[min(chan), max(chan)]
    ).coef
    pf = [round(f, args.precision) for f in pf]
    print(f"x^0 .. x^{args.order}: {pf}")
    rsquared(chan, energy, pf)


if __name__ == "__main__":
    main()
