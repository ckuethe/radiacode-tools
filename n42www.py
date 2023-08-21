#!/usr/bin/env python3

from flask import Flask, request, abort, send_file
from argparse import ArgumentParser, Namespace
from logging import Logger, getLogger, DEBUG, INFO, WARNING, basicConfig
from n42convert import process_single_fileobj
import os
from re import sub as resub
from io import BytesIO

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
        converted = process_single_fileobj(fileobj=upload.stream)
    except KeyboardInterrupt:
        raise
    except Exception:
        abort(400)

    filename = os.path.basename(upload.filename).removesuffix(".xml")
    filename = resub("[^a-zA-Z0-9_.-]", "_", filename)
    filename = resub("_+", "_", filename) + ".n42"

    return send_file(
        BytesIO(converted.encode()),
        mimetype="application/octet-stream",
        attachment_filename=filename,
        cache_timeout=1,
    )


def get_args() -> Namespace:
    ap = ArgumentParser()

    def _port_num(x):
        i = int(x)
        if 0 < x < 65535:
            return i
        raise ValueError("invalid port number")

    ap.add_argument("-b", "--bind-addr", type=str, default="0.0.0.0")
    ap.add_argument("-m", "--max-size", type=int, default=128 * 1024)
    ap.add_argument("-p", "--port", default=6853, type=_port_num)  # spells "NUKE" on a phone keypad
    ap.add_argument("-v", "--verbose", action="count", default=0)

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
    n42srv.run(host=args.bind_addr, port=args.port, load_dotenv=False, debug=wwwdebug)


if __name__ == "__main__":
    main()
