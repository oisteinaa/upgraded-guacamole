"""Directory replay for demonstrations. No recording/event database writes."""

import argparse
from concurrent.futures import ThreadPoolExecutor, wait as wait_for_futures
import fcntl
import hashlib
import json
import logging
import os
from pathlib import Path
import signal
import tempfile
import threading
import time

from .db import ROOT, rows
from .live import snapshot_path, write_snapshot
from .live_summary import profile_summary, recording_summary
from .metrics import VERSION as METRIC_VERSION, fibre_positions, map_metrics, metric_frame
from .signals import inspect_recording

VERSION = "demo-v2"
log = logging.getLogger(__name__)


def cache_root():
    return Path(os.getenv("DAS_DEMO_CACHE", ROOT / ".local/demo-cache"))


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, allow_nan=False, separators=(",", ":"))
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def source_files(directory):
    return sorted((path for path in directory.rglob("*")
                   if path.is_file() and path.suffix.lower() in (".h5", ".hdf5")
                   and path.resolve().is_relative_to(directory)),
                  key=lambda path: str(path.relative_to(directory)))


def mapping_context(lid=None):
    lids = [row["lid"] for row in rows("SELECT DISTINCT lid FROM masteliste ORDER BY lid")]
    if lid is not None and lid not in lids:
        raise ValueError(f"Unknown demo instrument lid {lid}")
    lid = lid if lid is not None else lids[0] if len(lids) == 1 else None
    positions = fibre_positions(lid) if lid is not None else []
    fingerprint = hashlib.sha256(json.dumps(positions, sort_keys=True).encode()).hexdigest()
    return lid, fingerprint


def prepare_file(path, lid, mapping_fingerprint):
    stat = path.stat()
    from .calm import identity as baseline_identity, live_activity
    identity = [VERSION, baseline_identity(), METRIC_VERSION, str(path.resolve()), stat.st_size, stat.st_mtime_ns,
                lid, mapping_fingerprint]
    token = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    summary_path = cache_root() / f"{token}.summary.json"
    metric_path = cache_root() / f"{token}.metrics.json"
    if summary_path.exists():
        try:
            result = json.loads(summary_path.read_text())
            if result.get("demo_token") == token and (not result.get("demo_has_metric") or metric_path.exists()):
                after = path.stat()
                if (after.st_size, after.st_mtime_ns) != (stat.st_size, stat.st_mtime_ns):
                    raise ValueError("Recording changed during demo preparation")
                return result
        except (OSError, json.JSONDecodeError):
            log.warning("Rebuilding unreadable demo cache for %s", path.name)
    recording = inspect_recording(path)
    # Synthetic IDs identify display cache entries only, never database rows.
    recording.update(id=-int(token[:12], 16), lid=lid, time_verified=False,
                     mapping_verified=False, processing="stored values × dataScale")
    rms, _, heatmap = recording_summary(recording)
    frame = metric_frame(recording, 0)
    try:
        profile = dict(status="complete", start=frame["start"], end=frame["end"],
                       **profile_summary(recording["channels"], frame["values"]["ac_rms"]))
    except ValueError as exc:
        profile = {"status": "unavailable", "note": str(exc)}
    metric = None
    mapping_note = "No unambiguous instrument mapping; choose --demo-lid to display geography."
    if lid is not None:
        metric = map_metrics(recording, lid, frame=0, metric="ac_rms", illustrative=True)
        mapping_note = "Illustrative positions from the current channel mapping; historical alignment is unverified."
        write_json(metric_path, metric)
    result = {
        "normalization": live_activity(recording, illustrative=True),
        "summary_version": 1, "recording_id": recording["id"], "frame": 0,
        "frame_count": frame["frame_count"], "metric_processing": frame["processing"],
        "filename": str(path.relative_to(Path(os.environ["DAS_ARCHIVE_ROOT"]))),
        "lid": lid, "duration": recording["samples"] * recording["dt"],
        "acquisition_epoch": recording["acquisition_epoch"],
        "time_verified": False, "mapping_verified": False,
        "unit": recording["unit"], "processing": recording["processing"],
        "channel_count": len(recording["channels"]), "points": [],
        "profile": profile, "heatmap": heatmap,
        "rms_min": float(rms.min()), "rms_max": float(rms.max()),
        "demo_token": token, "demo_has_metric": metric is not None,
        "demo_mapping_note": mapping_note,
        "detection": {"status": "disabled", "note": "Detection is disabled during demo replay. No events are created."},
    }
    after = path.stat()
    if (after.st_size, after.st_mtime_ns) != (stat.st_size, stat.st_mtime_ns):
        raise ValueError("Recording changed during demo preparation")
    write_json(summary_path, result)
    return result


def run_demo(directory, interval, stop, lid=None):
    # Only this child process uses the selected directory as its archive root.
    # Investigation continues using the API process's original archive settings.
    directory = directory.resolve(strict=True)
    os.environ["DAS_ARCHIVE_ROOT"] = str(directory)
    lid, mapping_fingerprint = mapping_context(lid)
    previous = None
    cycle = 0

    def publish(payload=None, **fields):
        write_snapshot(dict(payload or {"points": [], "demo_loading": True},
                            demo=True, replay=True, demo_source=str(directory),
                            demo_interval=interval, published_at=time.time(), **fields))

    def keep_visible(duration):
        until = time.monotonic() + duration
        while not stop.is_set() and time.monotonic() < until:
            publish(previous)
            stop.wait(min(2, max(0, until - time.monotonic())))

    publish(note="Preparing the first demo recording…")
    with ThreadPoolExecutor(max_workers=1) as executor:
        while not stop.is_set():
            paths = source_files(directory)
            cycle += 1
            successes = 0
            for index, path in enumerate(paths, 1):
                if stop.is_set():
                    break
                future = executor.submit(prepare_file, path, lid, mapping_fingerprint)
                while not future.done() and not stop.is_set():
                    publish(previous, demo_preparing=True, note=f"Preparing {path.name}…")
                    wait_for_futures([future], timeout=2)
                if stop.is_set():
                    break
                try:
                    payload = future.result()
                except (OSError, ValueError, KeyError) as exc:
                    log.warning("Skipping demo file %s: %s", path, exc)
                    continue
                previous = dict(payload, demo_position=index, demo_count=len(paths), demo_cycle=cycle)
                successes += 1
                log.info("Demo cycle %s · %s/%s · %s", cycle, index, len(paths), path.name)
                keep_visible(interval)
            if not successes and not stop.is_set():
                previous = None
                publish(note="No readable completed HDF5 files. Waiting and rescanning the demo directory.")
                stop.wait(max(interval, 5))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--interval", type=float, default=10)
    parser.add_argument("--lid", type=int)
    args = parser.parse_args()
    if not args.directory.is_dir() or not 5 <= args.interval <= 300:
        parser.error("Choose an existing directory and an interval from 5 to 300 seconds")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    lock_path = snapshot_path().with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        run_demo(args.directory, args.interval, stop, args.lid)


if __name__ == "__main__":
    main()
