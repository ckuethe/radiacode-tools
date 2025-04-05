#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# Author: Chris Kuethe <chris.kuethe@gmail.com> , https://github.com/ckuethe/radiacode-tools
# SPDX-License-Identifier: MIT

from argparse import ArgumentParser, Namespace
from math import pow, sqrt
from typing import Dict

from radiacode_tools.rc_files import RcSpectrum
from radiacode_tools.rc_types import DTstats, Number


def get_args() -> Namespace:
    ap = ArgumentParser()
    ap.add_argument(
        "-a",
        "--first",
        type=str,
        required=True,
        metavar="RCXML_OR_NUM",
        help="path to spectrum file; counts-per-interval; counts-per-second",
    )
    ap.add_argument("-b", "--second", type=str, required=True, metavar="RCXML_OR_NUM")
    ap.add_argument("-c", "--combined", type=str, required=True, metavar="RCXML_OR_NUM")
    ap.add_argument("-g", "--background", type=str, required=False, metavar="RCXML_OR_NUM")
    ap.add_argument("-i", "--interval", type=float, required=False, default=1.0, metavar="TIME", help="[%(default)ss]")
    return ap.parse_args()


def get_rate_from_spectrum(fn: str) -> float:
    return RcSpectrum(fn).count_rate()


def load_spectra(args) -> Dict[str, float]:
    rv = {}

    try:
        rv["a"] = float(args.first) / args.interval
    except ValueError:
        # file deepcode ignore PT: CLI tool intentionally opening the files the user asked for
        rv["a"] = get_rate_from_spectrum(args.first)

    try:
        rv["b"] = float(args.second) / args.interval
    except ValueError:
        rv["b"] = get_rate_from_spectrum(args.second)

    try:
        rv["ab"] = float(args.combined) / args.interval
    except ValueError:
        rv["ab"] = get_rate_from_spectrum(args.combined)

    if args.background is not None:
        try:
            rv["bg"] = float(args.background) / args.interval
        except ValueError:
            rv["bg"] = get_rate_from_spectrum(args.background)
    else:
        rv["bg"] = 0

    print(f"Computing deadtime from a={args.first}, b={args.second}, ab={args.combined}")

    return rv


# I know: x**2 == math.pow(x,2) , and x**0.5 == math.sqrt(x)
# but sqrt(x) is nicer to read than x**0.5, so I might as well use pow() too
#
# Knoll recommends use of sources with enough activity such that tau * ab >= 20%
# https://www.amazon.com/Radiation-Detection-Measurement-Glenn-Knoll/dp/0470131489
# pp. 122-123, Eq. (4.32) and (4.33)


def compute_deadtime(*, a: Number, b: Number, ab: Number, bg: Number = 0) -> DTstats:
    """
    compute the deadtime of a detector using the two source method.
    a: count rate of the first source measured alone
    b: count rate of the second source measured alone
    ab: count rate of both sources measured together
    bg: count rate of background radiation in the test environment
    """
    if bg < 0:
        raise ValueError("Background cannot be negative")

    if any([a <= 0, b <= 0, ab <= 0]):
        raise ValueError("Source counts must be greater than zero")

    X = a * b - bg * ab
    Y = a * b * (ab + bg) - bg * ab * (a + b)
    Z = Y * (a + b - ab - bg) / pow(X, 2)
    tau = X * (1 - sqrt(1 - Z)) / Y

    lost_counts = a + b - ab
    loss_fraction = 1 - ab / (a + b)
    return DTstats(lost_cps=lost_counts, loss_fraction=loss_fraction, dt_us=tau, dt_cps=ab)


def print_deadtime(rates: Dict[str, Number]) -> DTstats:
    "Given a dict of a,b,ab,bg rates, print the computed deadtime."
    dt = compute_deadtime(**rates)
    print(rates)
    print(f"dead time at {dt.dt_cps:.1f}cps: {dt.dt_us*1e6:.1f}us")
    print(f"lost count/sec: {dt.lost_cps:.1f} loss_fraction: {100*dt.loss_fraction:.1f}%")
    return dt


def main():
    args = get_args()
    rates = load_spectra(args)
    print_deadtime(rates)


if __name__ == "__main__":
    main()
