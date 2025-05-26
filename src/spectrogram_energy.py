#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# Author: Chris Kuethe <chris.kuethe@gmail.com> , https://github.com/ckuethe/radiacode-tools
# SPDX-License-Identifier: MIT

"""compute the energy in a radiacode spectrogram (or list of spectrograms)"""

import os
import sys
from argparse import ArgumentParser, Namespace

from radiacode_tools.rc_files import RcSpectrogram
from radiacode_tools.rc_types import SpecEnergy
from radiacode_tools.rc_utils import get_dose_from_spectrum


def get_args() -> Namespace:
    """The usual argparse stuff"""
    ap: ArgumentParser = ArgumentParser(description="Poll a RadiaCode PSRD and produce an N42 file")
    ap.add_argument("-r", "--recursive", default=False, action="store_true")
    ap.add_argument("-v", "--verbose", default=False, action="store_true")
    ap.add_argument(dest="files", nargs="*", default="", help="Files to parse")
    rv: Namespace = ap.parse_args()

    return rv


def load_spectrogram(fn: str) -> SpecEnergy:
    """Open a spectrogram"""
    total_energy: float = 0.0
    peak_dose_rate: float = 0.0

    sp: RcSpectrogram = RcSpectrogram(fn)
    for s in sp.samples:
        acc_time: float = s.td.total_seconds()
        nc: int = len(s.counts)
        if nc < sp.channels:  # pad to the right number of channels
            s.counts.extend([0] * (sp.channels - nc))
        dose: float = get_dose_from_spectrum(s.counts, sp.calibration)  # pyrefly: ignore bad-argument-type
        peak_dose_rate = max(peak_dose_rate, dose / acc_time)
        total_energy += dose

    return SpecEnergy(dose=total_energy, duration=sp.accumulation_time, peak_dose=peak_dose_rate)


def main() -> None:
    args: Namespace = get_args()
    s_per_hr = 3600

    if args.recursive:
        found_files: list[str] = []
        for d in args.files:
            print(f"scanning {d}")
            # file deepcode ignore PT: CLI tool intentionally opening the files the user asked for
            for root, _, files in os.walk(d):
                found_files.extend([os.path.join(root, f) for f in files])
        args.files = found_files  # pyrefly: ignore missing-attribute

    for fn in args.files:
        try:
            sp: SpecEnergy = load_spectrogram(fn)
            rate: float = s_per_hr * sp.dose / sp.duration.total_seconds()
            print(
                f"{fn}: {sp.dose:.2f}uSv in {int(sp.duration.total_seconds())}s | {rate:.2f}uSv/hr | peak: {sp.peak_dose*s_per_hr:.2f}uSv/hr"
            )
        except KeyboardInterrupt:
            return  # make ^C work
        except Exception as e:
            if args.verbose:
                print(f"{e} while processing '{fn}'", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
