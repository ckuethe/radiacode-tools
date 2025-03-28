#!/usr/bin/env python3
# coding: utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 syn=python
# Author: Chris Kuethe <chris.kuethe@gmail.com> , https://github.com/ckuethe/radiacode-tools
# SPDX-License-Identifier: MIT

import os
from argparse import ArgumentParser, Namespace
from io import BytesIO
from logging import DEBUG, INFO, WARNING, Logger, basicConfig, getLogger
from re import sub as re_sub

from flask import Flask, abort, request, send_file

from radiacode_tools.rc_files import RcN42, RcSpectrum

appname = "N42Server"
logger: Logger = getLogger(appname)
n42srv = Flask(appname)


input_name = "file-input"


@n42srv.route("/")
def handle_index():
    page = f"""
    <h2>Radiacode to N42 Converter</h2>


    <form action="convert" method="POST" enctype="multipart/form-data">
        <label for="{input_name}"> Select a Radiacode XML spectrum file to convert to N42<br></label>
        <input id="{input_name}" name="{input_name}" type="file" />
        <button id="upload-button">Upload</button>
    </form>
    """

    return page


@n42srv.route("/convert", methods=["POST"])
def handle_convert():
    uploads = list(request.files.keys())
    if uploads != [input_name]:
        abort(400)

    upload = request.files[input_name]
    try:
        sp = RcSpectrum()
        n42 = RcN42()
        sp.load_str(upload.stream.read())
        n42.from_rcspectrum(sp)
        converted = n42.generate_xml()

    except KeyboardInterrupt:
        raise
    except Exception:
        abort(400)

    filename = os.path.basename(upload.filename).removesuffix(".xml")
    filename = re_sub("[^a-zA-Z0-9_.-]", "_", filename)
    filename = re_sub("_+", "_", filename) + ".n42"

    return send_file(
        BytesIO(converted.encode()),
        mimetype="application/octet-stream",
        download_name=filename,
        max_age=1,
    )


def get_args() -> Namespace:
    ap = ArgumentParser()

    def _port_num(x) -> int:
        i = int(x)
        if 0 < i < 65536:
            return i
        raise ValueError("invalid port number")

    ap.add_argument(
        "-b",
        "--bind-addr",
        type=str,
        metavar="IP",
        default="127.0.0.1",
        help="IP address on which to listen [%(default)s]",
    )
    ap.add_argument(
        "-m",
        "--max-size",
        type=int,
        metavar="NUM",
        default=128 * 1024,
        help="Maximum upload file size in bytes [%(default)s]",
    )
    ap.add_argument(
        "-p",
        "--port",
        default=6853,  # spells "NUKE" on a phone keypad
        metavar="PORT",
        type=_port_num,
        help="Port on which to listen [%(default)s]",
    )
    ap.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="increase verbosity for debugging",
    )

    return ap.parse_args()


def main() -> None:
    args = get_args()

    loglevel = WARNING
    wwwdebug = False
    if args.verbose:
        if args.verbose < 2:
            loglevel = INFO
        else:
            loglevel = DEBUG
            args.bind_addr = "127.0.0.1"  # Only listen on localhost if debug mode is enabled
            wwwdebug = True

    basicConfig(level=loglevel)
    n42srv.config["MAX_CONTENT_LENGTH"] = args.max_size
    # file deepcode ignore RunWithDebugTrue: Bind address is set to localhost when debug is enabled
    n42srv.run(
        host=args.bind_addr,
        port=args.port,
        load_dotenv=False,
        debug=wwwdebug,  # codeql[py/flask-debug]
    )


if __name__ == "__main__":
    main()
