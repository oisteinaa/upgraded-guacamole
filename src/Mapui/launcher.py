"""Start the API and optionally supervise a demo or live ZMQ publisher."""

import argparse
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from .db import ROOT


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", metavar="DIRECTORY", type=Path, default=os.getenv("DAS_DEMO_DIR"),
                        help="Loop HDF5 files from DIRECTORY in the live monitor")
    parser.add_argument("--no-demo", dest="demo", action="store_const", const=None,
                        help="Disable demo even when DAS_DEMO_DIR is configured")
    parser.add_argument("--demo-interval", type=float, default=os.getenv("DAS_DEMO_INTERVAL", "10"),
                        help="Seconds to display each file (5–300, default 10)")
    parser.add_argument("--demo-lid", type=int, default=os.getenv("DAS_DEMO_LID"),
                        help="Illustrative instrument mapping; automatic when only one lid exists")
    parser.add_argument("--live-zmq", default=os.getenv("DAS_LIVE_ZMQ_BIND"),
                        metavar="ENDPOINT", help="Bind a completed-file ZMQ receiver")
    parser.add_argument("--live-lid", type=int, default=os.getenv("DAS_LIVE_LID"))
    parser.add_argument("--confirm-live-time", action="store_true",
                        default=os.getenv("DAS_LIVE_TIME_VERIFIED") == "1")
    parser.add_argument("--confirm-live-mapping", action="store_true",
                        default=os.getenv("DAS_LIVE_MAPPING_VERIFIED") == "1")
    args = parser.parse_args(argv)
    if args.demo is not None and args.live_zmq:
        parser.error("Demo replay and live ZMQ cannot run together; use --no-demo")
    if args.confirm_live_mapping and args.live_lid is None:
        parser.error("Verified live mapping requires --live-lid")
    if not 5 <= args.demo_interval <= 300:
        parser.error("--demo-interval must be from 5 to 300 seconds")
    if args.demo is not None:
        args.demo = args.demo.expanduser().resolve()
        if not args.demo.is_dir():
            parser.error("--demo must name an existing directory")
    return args


def main():
    args = arguments()
    command = [sys.executable, "-m", "uvicorn", "src.Mapui.api:app", "--host",
               os.getenv("DAS_BIND_HOST", "127.0.0.1"), "--port", os.getenv("DAS_PORT", "8051")]
    if args.demo is None:
        os.environ.pop("DAS_DEMO_ENABLED", None)
    if args.demo is None and not args.live_zmq:
        os.execv(sys.executable, command)
    if args.live_zmq:
        publisher = [sys.executable, "-u", "-m", "src.Capture.capture_zmq",
                     "--bind", args.live_zmq, "--latest-only"]
        if args.live_lid is not None:
            publisher.extend(["--lid", str(args.live_lid)])
        if args.confirm_live_time:
            publisher.append("--confirm-time")
        if args.confirm_live_mapping:
            publisher.append("--confirm-mapping")
    else:
        token = hashlib.sha256(str(args.demo).encode()).hexdigest()[:12]
        os.environ["DAS_DEMO_ENABLED"] = "1"
        os.environ["DAS_ENVIRONMENT"] = os.getenv("DAS_ENVIRONMENT", "Local") + " · Demo replay"
        os.environ["DAS_LIVE_SNAPSHOT"] = str(ROOT / f".local/demo-{token}.json")
        from .live import write_snapshot
        write_snapshot({"demo": True, "replay": True, "points": [], "demo_loading": True,
                        "published_at": time.time(), "demo_source": str(args.demo),
                        "note": "Starting demo replay…"})
        publisher = [sys.executable, "-m", "src.Mapui.demo", "--directory", str(args.demo),
                "--interval", str(args.demo_interval)]
        if args.demo_lid is not None:
            publisher.extend(["--lid", str(args.demo_lid)])
    children = []
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        children.append(subprocess.Popen(publisher))
        children.append(subprocess.Popen(command))
        while not stopping:
            if any(child.poll() is not None for child in children):
                return 1
            time.sleep(.25)
        return 0
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
