#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# Author: Chris Kuethe <chris.kuethe@gmail.com> , https://github.com/ckuethe/radiacode-tools
# SPDX-License-Identifier: MIT

"""compute the energy in a radiacode spectrogram (or list of spectrograms)"""

import os
import struct
import sys
from argparse import ArgumentParser, Namespace
from binascii import unhexlify

from rctypes import EnergyCalibration, SGHeader, SpecEnergy
from rcutils import FileTime2DateTime, get_dose_from_spectrum


def get_args() -> Namespace:
    """The usual argparse stuff"""
    ap = ArgumentParser(description="Poll a RadiaCode PSRD and produce an N42 file")
    ap.add_argument("-r", "--recursive", default=False, action="store_true")
    ap.add_argument("-v", "--verbose", default=False, action="store_true")
    ap.add_argument(dest="files", nargs="*", default="", help="Files to parse")
    rv = ap.parse_args()

    return rv


def parse_header(s: str) -> SGHeader:
    """Parse the header line into some useful properties"""
    rv = dict([w.split(": ") for w in s.strip("\n").split("\t")])
    # 64 is 256 downsampled by 4, and 1024 is the max channels we know about in a radiacode right now
    if 64 <= int(rv["Channels"]) <= 1024:
        return SGHeader(
            rv["Spectrogram"],
            rv["Time"],
            FileTime2DateTime(rv["Timestamp"]),
            int(rv["Channels"]),
            int(rv["Accumulation time"]),
            int(rv["Flags"]),
            rv["Comment"],
        )
    else:
        raise ValueError("Inapproprate number of channels")


def extract_calibration_from_spectrum(s: str) -> EnergyCalibration:
    """The 'Spectrum:' line has the energy calibration factors in it (among other things)"""
    spectrum_data = s.replace("Spectrum:", "").replace(" ", "").strip()
    raw_data = unhexlify(spectrum_data)[:16]
    fmt = f"<I3f"
    tmp = struct.unpack(fmt, raw_data)
    return EnergyCalibration(*tmp[1:])


def load_spectrogram(fn: str) -> SpecEnergy:
    """Open a spectrogram"""
    cal: EnergyCalibration = None
    header: SGHeader = SGHeader()
    total_energy: float = 0.0
    peak_dose_rate: float = 0.0

    with open(fn) as ifd:
        for line in ifd:
            if line.startswith("Spectrogram:") and not header.name:
                header = parse_header(line)
            elif line.startswith("Spectrum:") and cal is None:
                cal = extract_calibration_from_spectrum(line)
            else:
                _, acc_time, *counts = line.strip().split("\t")
                acc_time = int(acc_time)
                counts = [int(c) for c in counts]
                if len(counts) < header.channels:  # pad to the right number of channels
                    counts.extend([0] * (header.channels - len(counts)))
                dose = get_dose_from_spectrum(counts, *cal)
                peak_dose_rate = max(peak_dose_rate, dose / acc_time)
                total_energy += dose

        return SpecEnergy(total_energy, header.duration, peak_dose_rate)


def main() -> None:
    args = get_args()
    s_per_hr = 3600

    if args.recursive:
        found_files = []
        for d in args.files:
            print(f"scanning {d}")
            # file deepcode ignore PT: CLI tool intentionally opening the files the user asked for
            for root, _, files in os.walk(d):
                found_files.extend([os.path.join(root, f) for f in files])
        args.files = found_files

    for fn in args.files:
        try:
            sp = load_spectrogram(fn)
            rate = s_per_hr * sp.dose / sp.duration
            print(
                f"{fn}: {sp.dose:.2f}uSv in {sp.duration}s | {rate:.2f}uSv/hr | peak: {sp.peak_dose*s_per_hr:.2f}uSv/hr"
            )
        except KeyboardInterrupt:
            return  # make ^C work
        except Exception as e:
            if args.verbose:
                print(f"{e} while processing '{fn}'", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
