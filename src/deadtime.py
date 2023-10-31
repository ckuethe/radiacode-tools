#!/usr/bin/env python
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

from argparse import ArgumentParser, Namespace
from math import pow, sqrt
from typing import Union, Dict, Any
from sys import exit
import n42convert

Number = Union[int, float]


def get_args() -> Namespace:
    ap = ArgumentParser()
    ap.add_argument("-a", "--first", type=str, required=True, metavar="RCXML", help="path to Radiacode XML spectrum")
    ap.add_argument("-b", "--second", type=str, required=True, metavar="RCXML")
    ap.add_argument("-c", "--combined", type=str, required=True, metavar="RCXML")
    ap.add_argument("-g", "--background", type=str, required=False, metavar="RCXML")
    return ap.parse_args()


def load_spectra(args) -> Dict[str, float]:
    rv = {}

    s = n42convert.load_radiacode_spectrum(args.first)
    rv["a"] = sum(s["foreground"]["spectrum"]) / s["foreground"]["duration"]

    s = n42convert.load_radiacode_spectrum(args.second)
    rv["b"] = sum(s["foreground"]["spectrum"]) / s["foreground"]["duration"]

    s = n42convert.load_radiacode_spectrum(args.combined)
    rv["ab"] = sum(s["foreground"]["spectrum"]) / s["foreground"]["duration"]

    if args.background:
        s = n42convert.load_radiacode_spectrum(args.background)
        rv["bg"] = sum(s["foreground"]["spectrum"]) / s["foreground"]["duration"]
    else:
        rv["bg"] = 0

    return rv


# I know: x**2 == math.pow(x,2) , and x**0.5 == math.sqrt(x)
# but sqrt(x) is nicer to read than x**0.5, so I might as well use pow() too
#
# Knoll recommends use of sources with enough activity such that tau * ab >= 20%
# https://www.amazon.com/Radiation-Detection-Measurement-Glenn-Knoll/dp/0470131489
# pp. 122-123, Eq. (4.32) and (4.33)


def compute_tau(a: Number, b: Number, ab: Number, bg: Number = 0) -> float:
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
    return tau


def compute_loss(spectra: Dict[str, Number]) -> float:
    lost_counts = spectra["a"] + spectra["b"] - spectra["ab"]
    loss_fraction = 1 - spectra["ab"] / (spectra["a"] + spectra["b"])
    print(f"lost count/sec: {lost_counts:.1f} loss_fraction: {100*loss_fraction:.1f}%")
    return loss_fraction


def compute_deadtime(spectra: Dict[str, Number]) -> float:
    tau = compute_tau(spectra["a"], spectra["b"], spectra["ab"], spectra["bg"])
    print(f"dead time at {spectra['ab']:.1f}cps: {tau*1e6:.1f}us")
    return tau


def main():
    args = get_args()
    spectra = load_spectra(args)
    compute_loss(spectra)
    compute_deadtime(spectra)


if __name__ == "__main__":
    main()
