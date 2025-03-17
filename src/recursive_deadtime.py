#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# Author: Chris Kuethe <chris.kuethe@gmail.com> , https://github.com/ckuethe/radiacode-tools
# SPDX-License-Identifier: MIT

import os
from argparse import ArgumentParser, Namespace

import deadtime

_UNSET_ = "n0"  # a bare neutron, just as a string whose contents may be searched


def get_args() -> Namespace:
    ap = ArgumentParser(
        description="Walk a file hierarchy looking for datasets which might be used to compute deadtime"
    )
    ap.add_argument("-b", "--bgfile", type=str)
    ap.add_argument(nargs=1, dest="datadir", type=str)
    ap.epilog = "A target directory must have three files: (<source>)_a.xml, (<source>)_b.xml, and $1+$2.xml, eg. cs137_a.xml, eu152_b.xml, cs137_a+eu152_b.xml"
    args = ap.parse_args()
    args.datadir = args.datadir[0]
    return args


def process_dir(dirname, files, rate_bg=0) -> bool:
    print(f"\nProcessing {dirname}")
    n1 = _UNSET_
    n2 = _UNSET_
    n12 = _UNSET_
    files.sort()
    while files:
        fn = files.pop()
        nuc = fn.rstrip(".xml")
        if n2 == _UNSET_ and fn.endswith("_b.xml"):
            n2 = nuc
        if fn.endswith("_a.xml"):
            n1 = nuc
        if n1 in fn and n2 in fn:
            n12 = nuc

    rates = {
        "bg": rate_bg,
        "a": deadtime.get_rate_from_spectrum(os.path.join(dirname, f"{n1}.xml")),
        "b": deadtime.get_rate_from_spectrum(os.path.join(dirname, f"{n2}.xml")),
        "ab": deadtime.get_rate_from_spectrum(os.path.join(dirname, f"{n12}.xml")),
    }

    dt = deadtime.print_deadtime(rates)
    if dt.dt_us < 0:
        print("WARNING: bogus deadtime!")
        return False
    return True


def main() -> None:
    args = get_args()
    if args.bgfile:
        rate_bg = deadtime.get_rate_from_spectrum(args.bgfile)
    else:
        rate_bg = 0

    # file deepcode ignore PT: CLI tool intentionally opening the files the user asked for
    for rootdir, dirs, files in os.walk(args.datadir):
        if 3 == len(files):
            process_dir(rootdir, files, rate_bg=rate_bg)


if __name__ == "__main__":
    main()
