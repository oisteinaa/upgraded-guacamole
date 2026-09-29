#!/usr/bin/env python3
"""Index completed recordings and publish explicit-channel signal metrics.

Run with --replay for local archive playback or use the existing ZMQ completed-file
notification transport. No metric is interpreted as a verified event class.
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.Mapui.live import publish_recording
from src.Mapui.signals import archive_root, register_recording


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--replay", action="store_true")
    p.add_argument("--interval", type=float, default=10)
    p.add_argument("--bind", default="tcp://127.0.0.1:12345")
    p.add_argument("--lid", type=int)
    p.add_argument("--latest-only", action="store_true",
                   help="Coalesce queued notifications for a current live display")
    p.add_argument(
        "--rules", type=Path, help="Calibrated RMS rules for this signal representation"
    )
    p.add_argument(
        "--legacy-timezone",
        help="Verified legacy event writer timezone, e.g. Europe/Oslo",
    )
    p.add_argument("--confirm-time", action="store_true")
    p.add_argument("--confirm-mapping", action="store_true")
    args = p.parse_args()
    if args.interval < 0:
        p.error("interval must be nonnegative")
    if args.rules and not args.legacy_timezone:
        p.error("--rules requires --legacy-timezone")
    rules = json.loads(args.rules.read_text()) if args.rules else None

    def process(path):
        rid = register_recording(
            path, args.lid, args.confirm_time, args.confirm_mapping
        )
        summary = publish_recording(
            rid, replay=args.replay, rules=rules, legacy_timezone=args.legacy_timezone
        )
        print(
            f"Published recording {rid}: {summary['channel_count']} explicit channels",
            flush=True,
        )

    if args.replay:
        for path in sorted(archive_root().rglob("*.hdf5")):
            process(path)
            time.sleep(args.interval)
    else:
        import zmq

        with zmq.Context() as context:
            socket = context.socket(zmq.PULL)
            socket.bind(args.bind)
            while True:
                try:
                    message = socket.recv_json()
                    skipped = 0
                    if args.latest_only:
                        # Bound each drain so continuous senders cannot starve processing.
                        while skipped < 1000 and socket.poll(0, zmq.POLLIN):
                            message = socket.recv_json()
                            skipped += 1
                    if skipped:
                        print(f"Skipped {skipped} queued notifications for live freshness", flush=True)
                    process(message["dest_path"])
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    print(f"Rejected capture: {exc}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
