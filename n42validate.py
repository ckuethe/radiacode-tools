#!/usr/bin/env python3

from argparse import ArgumentParser, Namespace
import os
import requests
import defusedxml.ElementTree as ET
from xmlschema import XMLSchema
from tempfile import mkstemp


def fetch_or_load_xsd(schema_file="~/.cache/n42.xsd", schema_url="https://www.nist.gov/document/n42xsd") -> XMLSchema:
    schema_file = os.path.expanduser(schema_file)
    schema_dir = os.path.dirname(schema_file)
    os.makedirs(schema_dir, exist_ok=True)
    if not os.path.exists(schema_file):
        resp = requests.get(schema_url, timeout=10)
        if resp.ok:
            tfd, tfn = mkstemp(dir=schema_dir)
            print(tfn)
            os.close(tfd)
            with open(tfn, "w") as ofd:
                ofd.write(resp.text)
            os.rename(tfn, schema_file)
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
        "-v",
        "--verbose",
        default=False,
        action="store_true",
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
    for f in args.files:
        xml_doc = ET.parse(f)
        v = "OK"
        if schema.is_valid(xml_doc):
            if args.verbose:
                print(f"[VALID] {f}")
        else:
            print(f"[ERROR] {f}")
            try:
                schema.validate(xml_doc)
            except Exception as e:
                print(e)
            print("-" * 75)


if __name__ == "__main__":
    main()
