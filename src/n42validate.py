#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# SPDX-License-Identifier: MIT

import os
from argparse import ArgumentParser, Namespace
from tempfile import mkstemp

import defusedxml.ElementTree as ET
import requests
from xmlschema import XMLSchema


def fetch_or_load_xsd(schema_file="~/.cache/n42.xsd", schema_url="https://www.nist.gov/document/n42xsd") -> XMLSchema:
    schema_file = os.path.expanduser(schema_file)
    schema_dir = os.path.dirname(schema_file)
    os.makedirs(schema_dir, exist_ok=True)
    if not os.path.exists(schema_file) or 0 == os.path.getsize(schema_file):
        resp = requests.get(schema_url, timeout=10)
        if resp.ok:
            tfd, tfn = mkstemp(prefix="schema_", dir=schema_dir)
            print(tfn)
            os.close(tfd)
            # file deepcode ignore PT: CLI tool intentionally opening the files the user asked for
            with open(tfn, "w") as ofd:
                ofd.write(resp.text)
            os.rename(tfn, schema_file)
        else:
            raise RuntimeError("Unable to fetch schema")

    return XMLSchema(schema_file)


def get_args() -> Namespace:
    ap = ArgumentParser()

    ap.add_argument(
        "-r",
        "--recursive",
        default=False,
        action="store_true",
        help="treat the input path as a directory to process recursively [%(default)s]",
    )
    ap.add_argument(
        "-q",
        "--quiet",
        default=False,
        action="store_true",
        help="don't display the invalid XML element",
    )
    ap.add_argument(
        "-v",
        "--verbose",
        default=False,
        action="store_true",
        help="display valid files too, by default only invalid files are reported",
    )
    ap.add_argument(
        "-V",
        "--valid-only",
        default=False,
        action="store_true",
        help="only display valid files",
    )
    ap.add_argument(
        "-s",
        "--schema-file",
        default="~/.cache/n42.xsd",
        type=str,
        metavar="XSD",
        help="Default: %(default)s",
    )
    ap.add_argument(
        "-u",
        "--schema-url",
        default="https://www.nist.gov/document/n42xsd",
        type=str,
        metavar="URL",
        help="Default: %(default)s",
    )
    ap.add_argument(
        "-x",
        "--extension",
        default=".n42",
        type=str,
        metavar="EXT",
        help="Default: %(default)s",
    )
    ap.add_argument(
        nargs="+",
        type=str,
        metavar="FILE",
        dest="files",
        help="source data file",
    )

    return ap.parse_args()


def main() -> None:
    args = get_args()

    schema = fetch_or_load_xsd(schema_file=args.schema_file, schema_url=args.schema_url)

    workqueue = []
    if args.recursive:
        for f in args.files:
            for dirpath, _, filenames in os.walk(f):
                for filename in [fn for fn in filenames if fn.endswith(args.extension)]:
                    workqueue.append(os.path.join(dirpath, filename))
    else:
        workqueue = args.files

    for f in workqueue:
        xml_doc = ET.parse(f)
        if schema.is_valid(xml_doc):
            if args.verbose or args.valid_only:
                print(f"[VALID] {f}")
        else:
            if args.valid_only:
                continue
            print(f"[ERROR] {f}")
            if args.quiet:
                continue
            try:
                schema.validate(xml_doc)
            except Exception as e:
                print(e)
            print("-" * 75)


if __name__ == "__main__":
    main()
