"""Atomic file-backed snapshots shared by capture and multiple API workers."""

import json
import math
import os
import tempfile
import time
from pathlib import Path

import h5py
import numpy as np

from .db import ROOT, rows
from .signals import safe_path


def snapshot_path():
    return Path(os.getenv("DAS_LIVE_SNAPSHOT", ROOT / ".local/live.json"))


def publish_recording(recording_id, replay=False, rules=None, legacy_timezone=None):
    recording = rows("SELECT * FROM das_recordings WHERE id=%s", (recording_id,))[0]
    n = len(recording["channels"])
    sums = np.zeros(n)
    squares = np.zeros(n)
    with h5py.File(safe_path(recording["relative_path"]), "r") as f:
        for a in range(0, recording["samples"], 256):
            block = (
                np.asarray(f["data"][a : a + 256, :], dtype=np.float64)
                * recording["scale"]
            )
            if not np.all(np.isfinite(block)):
                raise ValueError("Nonfinite samples in live recording")
            sums += block.sum(axis=0)
            squares += (block * block).sum(axis=0)
    rms = np.sqrt(squares / recording["samples"])
    var = np.maximum(
        0, squares / recording["samples"] - (sums / recording["samples"]) ** 2
    )
    mapping = {}
    if recording["mapping_verified"] and recording["lid"] is not None:
        mapping = {
            m["channel"]: m
            for m in rows(
                "SELECT channel,latitude,longitude,gid FROM masteliste WHERE lid=%s",
                (recording["lid"],),
            )
        }
    # Screen-space aggregation happens at the browser; full explicit channel metrics stay available.
    points = []
    for i, ch in enumerate(recording["channels"]):
        if ch in mapping:
            points.append(
                dict(
                    channel=ch,
                    lid=recording["lid"],
                    rms=float(rms[i]),
                    variance=float(var[i]),
                    **{k: v for k, v in mapping[ch].items() if k != "channel"},
                )
            )
    from .metrics import metric_frame

    fixed = metric_frame(recording, 0)
    payload = {
        "recording_id": recording_id,
        "frame": 0,
        "frame_count": fixed["frame_count"],
        "metric_processing": fixed["processing"],
        "available_metrics": ["ac_rms", "band_rms", "peak", "variance"],
        "acquisition_epoch": recording["acquisition_epoch"],
        "published_at": time.time(),
        "replay": replay,
        "time_verified": recording["time_verified"],
        "mapping_verified": recording["mapping_verified"],
        "unit": recording["unit"],
        "processing": recording["processing"],
        "channel_count": n,
        "points": points,
        "rms_min": float(rms.min()),
        "rms_max": float(rms.max()),
    }
    if rules is not None:
        if not legacy_timezone:
            raise ValueError("Detection requires an explicit legacy writer timezone")
        from src.Capture.event_detector import detect_events

        payload["candidate_events"] = detect_events(
            recording,
            dict(zip(recording["channels"], rms.tolist())),
            rules,
            legacy_timezone,
        )
    target = snapshot_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=target.parent, delete=False) as f:
        json.dump(payload, f, allow_nan=False)
        temporary = f.name
    os.replace(temporary, target)
    return payload


def load_snapshot(max_points=3000):
    try:
        with snapshot_path().open() as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "status": "offline",
            "points": [],
            "note": "No capture has been published",
        }
    points = data["points"]
    data["source_points"] = len(points)
    if len(points) > max_points:
        width = math.ceil(len(points) / max(1, max_points // 2))
        reduced = []
        for start in range(0, len(points), width):
            bucket = points[start : start + width]
            # Keep actual minimum and maximum channels; never invent a position.
            selected = sorted(
                {
                    min(range(len(bucket)), key=lambda i: bucket[i]["rms"]),
                    max(range(len(bucket)), key=lambda i: bucket[i]["rms"]),
                }
            )
            reduced.extend(bucket[i] for i in selected)
        data["points"] = reduced
    data["display_points"] = len(data["points"])
    age = max(0, time.time() - data["published_at"])
    acquisition_age = max(0, time.time() - data["acquisition_epoch"])
    data.update(
        age_seconds=age,
        acquisition_age_seconds=acquisition_age,
        status="replay"
        if data["replay"]
        else "unverified"
        if not data["time_verified"]
        else "stale"
        if max(age, acquisition_age) > 30
        else "live",
    )
    return data
