"""Atomic file-backed snapshots shared by capture and multiple API workers."""

import json
import math
import os
import tempfile
import time
from pathlib import Path
from .db import ROOT, rows


def snapshot_path():
    return Path(os.getenv("DAS_LIVE_SNAPSHOT", ROOT / ".local/live.json"))


def publish_recording(recording_id, replay=False, rules=None, legacy_timezone=None):
    recording = rows("SELECT * FROM das_recordings WHERE id=%s", (recording_id,))[0]
    n = len(recording["channels"])
    from .live_summary import recording_summary, profile_summary

    rms, var, heatmap = recording_summary(recording)
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
    try:
        profile = dict(status="complete", **profile_summary(recording["channels"], fixed["values"]["ac_rms"]),
                       start=fixed["start"], end=fixed["end"])
    except ValueError as exc:
        profile = {"status": "unavailable", "note": str(exc)}
    payload = {
        "summary_version": 1,
        "filename": Path(recording["relative_path"]).name,
        "lid": recording["lid"],
        "duration": recording["samples"] * recording["dt"],
        "heatmap": heatmap,
        "profile": profile,
        "detection": {"status": "not_configured"},
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
    from .calm import live_activity
    payload["normalization"] = live_activity(recording)
    eligible = recording["time_verified"] and recording["mapping_verified"] and recording["lid"] is not None
    if rules is not None and not eligible:
        payload["detection"] = {"status": "unavailable", "note": "Detection requires verified acquisition time and instrument/channel mapping"}
    elif rules is not None:
        import logging
        from src.Capture.event_detector import detect_events

        payload["detection"] = {"status": "processing"}
        # Publish actual pending detection without withholding the current signal.
        write_snapshot(payload)
        try:
            if not legacy_timezone:
                raise ValueError("Detection requires an explicit legacy writer timezone")
            payload["candidate_events"] = detect_events(
                recording, dict(zip(recording["channels"], rms.tolist())),
                rules, legacy_timezone, assessment=payload["detection"],
            )
        except Exception:
            logging.getLogger(__name__).exception("Detection failed for recording %s", recording_id)
            payload["detection"] = {"status": "failed", "note": "Detection failed; check capture logs"}
    write_snapshot(payload)
    return payload


def write_snapshot(payload):
    target = snapshot_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=target.parent, delete=False) as f:
        json.dump(payload, f, allow_nan=False)
        temporary = f.name
    os.replace(temporary, target)


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
    acquisition_age = max(0, time.time() - data["acquisition_epoch"]) if data.get("acquisition_epoch") is not None else None
    if data.get("demo") and os.getenv("DAS_DEMO_ENABLED") == "1":
        data.update(age_seconds=age, acquisition_age_seconds=acquisition_age,
                    status="demo_stale" if age > 30 else "demo_loading" if data.get("demo_loading") else "demo")
        return data
    data.update(
        age_seconds=age,
        acquisition_age_seconds=acquisition_age,
        status="replay"
        if data["replay"]
        else "unverified"
        if not data["time_verified"]
        else "stale"
        if acquisition_age is None or max(age, acquisition_age) > 30
        else "live",
    )
    return data
