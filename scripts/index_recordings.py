#!/usr/bin/env python3
"""Index local archive metadata; no inferred event links or classes."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.Mapui.signals import archive_root, register_recording


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lid", type=int)
    parser.add_argument(
        "--confirm-time",
        action="store_true",
        help="Only after independently verifying header Unix timestamps",
    )
    parser.add_argument(
        "--confirm-mapping",
        action="store_true",
        help="Only after verifying instrument lid and explicit channel IDs",
    )
    args = parser.parse_args()
    successes, failures = [], []
    for path in sorted(archive_root().rglob("*")):
        if path.suffix.lower() not in (".h5", ".hdf5"):
            continue
        try:
            successes.append(
                {
                    "file": path.name,
                    "id": register_recording(
                        path, args.lid, args.confirm_time, args.confirm_mapping
                    ),
                }
            )
        except (ValueError, OSError, KeyError) as exc:
            failures.append({"file": path.name, "error": str(exc)})
    print(json.dumps({"indexed": successes, "rejected": failures}, indent=2))
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
