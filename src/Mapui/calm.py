"""Fixed calm-weather references. Scores are departures, never event labels.

Artifacts contain only JSON and numeric numpy arrays (no pickle). Normalization
always precedes display reduction and uses the metric calculator's source frames.
"""
import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path

import numpy as np

from .db import ROOT

VERSION = "calm-mad-v1"


def artifact_root():
    return Path(os.getenv("DAS_CALM_BASELINES", ROOT / ".local/calm-baselines"))


def fingerprint(recording):
    from .stitched_signals import configuration
    return hashlib.sha256(json.dumps(configuration(recording), sort_keys=True).encode()).hexdigest()


@lru_cache(maxsize=4)
def _load(path, mtime):
    meta = json.loads(Path(path).read_text())
    if meta["version"] != VERSION:
        raise ValueError("Unsupported calm baseline version")
    return meta


def active():
    path = artifact_root() / "active.json"
    try:
        return _load(str(path), path.stat().st_mtime_ns)
    except (OSError, ValueError, KeyError):
        return None


def identity():
    return (active() or {}).get("id", "none")


@lru_cache(maxsize=8)
def _arrays(path, mtime):
    with np.load(path, allow_pickle=False) as f:
        return {k: f[k] for k in f.files}


def unavailable(note):
    return {"status": "unavailable", "note": note, "available_channels": 0}


def reference(recording, illustrative=False):
    meta = active()
    if meta is None:
        return unavailable("No calm baseline has been activated"), None
    if not illustrative and not recording.get("mapping_verified"):
        return unavailable("Calm reference requires verified instrument/channel mapping"), None
    try:
        key = fingerprint(recording)
        config = meta["configurations"].get(key)
        if config is None:
            return unavailable("No calm reference matches this acquisition configuration"), None
        filename = config["file"]
        if Path(filename).name != filename:
            raise ValueError("Invalid artifact path")
        path = artifact_root() / filename
        arrays = _arrays(str(path), path.stat().st_mtime_ns)
        if not np.array_equal(arrays["channels"], recording["channels"]):
            raise ValueError("Baseline channel identities differ")
        return {"status": "available", "baseline_id": meta["id"],
                "training_start": config.get("training_start", meta["training_start"]),
                "training_end": config.get("training_end", meta["training_end"]),
                "available_channels": int(np.count_nonzero(arrays["eligible"])),
                "total_channels": len(recording["channels"]), "band": meta["band"],
                "illustrative": illustrative, "configuration": key,
                "note": "Departure from calm reference; not an event probability"}, arrays
    except (OSError, ValueError, KeyError) as exc:
        return unavailable(str(exc)), None


def robust_fit(values):
    median = np.median(values, axis=0)
    mad = np.median(np.abs(values - median), axis=0)
    scale = np.maximum(1.4826 * mad, .05 * median)
    return median, mad, scale


def score(values, median, scale, eligible):
    valid = np.asarray(eligible) & np.isfinite(scale) & (scale > 0)
    out = np.full(np.asarray(values).shape, np.nan, dtype=float)
    np.divide(np.asarray(values) - median, scale, out=out, where=valid)
    out[~np.isfinite(out)] = np.nan
    return out


def json_values(values):
    a = np.asarray(values)
    return np.where(np.isfinite(a), a, None).tolist()


def normalize_frame(recording, frame, metric="ac_rms", illustrative=False, ref=None):
    info, arrays = ref if ref is not None else reference(recording, illustrative)
    info = dict(info)
    if arrays is None:
        return info, np.full(len(recording["channels"]), np.nan)
    if not frame["complete"]:
        return unavailable("Partial analysis frame; raw measurements remain available"), np.full(len(recording["channels"]), np.nan)
    if metric == "band_rms" and list(frame["band"]) != info["band"]:
        return unavailable("This frequency band has no trained calm reference"), np.full(len(recording["channels"]), np.nan)
    z = score(frame["values"][metric], arrays[metric + "_median"], arrays[metric + "_scale"], arrays["eligible"])
    info["available_channels"] = int(np.isfinite(z).sum())
    info["status"] = "available" if np.isfinite(z).all() else "partial" if np.isfinite(z).any() else "unavailable"
    info["training_reference"] = [recording["relative_path"], frame["frame"]] in (active() or {}).get("configurations", {}).get(info["configuration"], {}).get("fit_frames", [])
    return info, z


def add_map_normalization(result, recording, frame, metric, illustrative=False):
    ref = reference(recording, illustrative)
    info, z = normalize_frame(recording, frame, metric, illustrative, ref)
    arrays = ref[1]
    columns = {ch: i for i, ch in enumerate(recording["channels"])}
    for feature in result["data"]["features"]:
        p = feature["properties"]
        i = columns[p["recording_channel"]]
        p["calm_score"] = float(z[i]) if np.isfinite(z[i]) else None
        p["calm_median"] = float(arrays[metric + "_median"][i]) if arrays is not None and np.isfinite(z[i]) else None
        p["calm_scale_floored"] = bool(arrays[metric + "_scale"][i] > 1.4826 * arrays[metric + "_mad"][i]) if p["calm_median"] is not None else None
    result["normalization"] = info


def activity(recordings, channels=None, start=None, end=None, epoch=None, illustrative=False):
    """Per-source-frame scores shared by live and stitched investigation.

    Each file retains its frame origin, even when a neighbour starts between
    nominal ten-second boundaries. Never score a synthetic stitched frame.
    """
    from .metrics import metric_frame, METRICS
    first = recordings[0]
    channels = first["channels"] if channels is None else channels
    columns = [first["channels"].index(ch) for ch in channels]
    epoch = first["acquisition_epoch"] if epoch is None else epoch
    info, arrays = reference(first, illustrative)
    if arrays is None:
        return info
    output = dict(info, channels=channels, times=[], starts=[], ends=[], training_frames=[], scores={m: [] for m in METRICS}, raw={m: [] for m in METRICS}, medians={m: json_values(arrays[m + "_median"][columns]) for m in METRICS})
    for rec in recordings:
        ref = (info, arrays) if rec is first else reference(rec, illustrative)
        width = max(1, round(10 / rec["dt"]))
        offset = rec["acquisition_epoch"] - epoch
        count = (rec["samples"] + width - 1) // width
        lo = max(0, int(np.floor(((start or 0) - offset) / (width * rec["dt"])))) if start is not None else 0
        hi = min(count, int(np.ceil((end - offset) / (width * rec["dt"])))) if end is not None else count
        for index in range(lo, hi):
            if min(width, rec["samples"] - index * width) < 8:
                continue
            a = offset + index * width * rec["dt"]
            b = offset + min(rec["samples"], (index + 1) * width) * rec["dt"]
            # Stitched sources accept timestamp rounding within one sample.
            # Do not include a neighbouring frame solely for that rounding sliver.
            if (start is not None and b <= start + rec["dt"]) or (end is not None and a >= end - rec["dt"]):
                continue
            frame = metric_frame(rec, index)
            a, b = offset + frame["start"], offset + frame["end"]
            output["starts"].append(a)
            output["ends"].append(b)
            output["times"].append((a + b) / 2)
            for metric in METRICS:
                status, z = normalize_frame(rec, frame, metric, illustrative, ref)
                output["scores"][metric].append(json_values(z[columns]))
                output["raw"][metric].append(frame["values"][metric][columns].tolist())
            output["training_frames"].append(status.get("training_reference", False))
    valid = np.asarray(output["scores"]["ac_rms"], dtype=float)
    output["available_channels"] = int(np.any(np.isfinite(valid), axis=0).sum()) if valid.size else 0
    output["total_channels"] = len(channels)
    output["status"] = "available" if output["available_channels"] == len(channels) and valid.size and np.isfinite(valid).all() else "partial" if output["available_channels"] else "unavailable"
    if not output["available_channels"]:
        output["note"] = "No complete frames with a qualified calm reference in this window"
    return output


def live_activity(recording, illustrative=False):
    from .live_summary import channel_groups
    value = activity([recording], illustrative=illustrative)
    if not value.get("available_channels") or "scores" not in value:
        return value
    groups, edges = channel_groups(recording["channels"])
    heat, peaks, raw_heat, median_heat = [], [], [], []
    for frame_index, frame in enumerate(value["scores"]["ac_rms"]):
        z = np.asarray(frame, dtype=float)
        row, ids, raw_row, median_row = [], [], [], []
        for group in groups:
            valid = [] if group is None else [int(i) for i in group if np.isfinite(z[i])]
            best = max(valid, key=lambda i: z[i]) if valid else None
            row.append(float(z[best]) if best is not None else None)
            ids.append(recording["channels"][best] if best is not None else None)
            raw_row.append(value["raw"]["ac_rms"][frame_index][best] if best is not None else None)
            median_row.append(value["medians"]["ac_rms"][best] if best is not None else None)
        heat.append(row)
        peaks.append(ids)
        raw_heat.append(raw_row)
        median_heat.append(median_row)
    # Retain gaps and extrema, with unavailable channels explicitly breaking lines.
    groups, _ = channel_groups(recording["channels"], 600)
    x, y, raw, medians = [], [], [], []
    z = np.asarray(value["scores"]["ac_rms"][0], dtype=float)
    for group in groups:
        valid = [] if group is None else [int(i) for i in group if np.isfinite(z[i])]
        if not valid:
            x.append(None); y.append(None); raw.append(None); medians.append(None)
            continue
        for i in sorted({min(valid, key=lambda i: z[i]), max(valid, key=lambda i: z[i])}, key=lambda i: recording["channels"][i]):
            x.append(recording["channels"][i]); y.append(float(z[i]))
            raw.append(value["raw"]["ac_rms"][0][i]); medians.append(value["medians"]["ac_rms"][i])
        if len(valid) != len(group):
            x.append(None); y.append(None); raw.append(None); medians.append(None)
    summary = {k: v for k, v in value.items() if k not in ("scores", "raw", "medians", "channels", "times", "starts", "ends")}
    summary["profile"] = dict(status="complete", channels=x, values=y, raw=raw, medians=medians, start=value["starts"][0], end=value["ends"][0])
    summary["heatmap"] = dict(status="complete", channel_edges=edges, time_edges=value["starts"] + [value["ends"][-1]], values=heat, peak_channels=peaks, raw=raw_heat, medians=median_heat, aggregation="Maximum per-channel calm score; complete ten-second source frames")
    return summary
