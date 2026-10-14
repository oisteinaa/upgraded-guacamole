"""Fixed-window, full-sample metrics shared by capture and map investigation.

Display reduction is separate from calculation. No metric is an event class.
"""

import bisect
import hashlib
import json
import math
import os
import tempfile
from pathlib import Path
from threading import Lock

import h5py
import numpy as np
from scipy.signal import welch

from .db import ROOT, rows
from .signals import safe_path

VERSION = "scaled-ac-v1"
WINDOW_SECONDS = 10.0
METRICS = ("ac_rms", "band_rms", "peak", "variance")
# Geometry remains on the original grid when acquisition decimation changes.
MAPPING_CHANNEL_STEP = 4
_calculation_lock = Lock()


def calculate_metrics(data, dt, low=1.0, high=10.0):
    """Samples × channels; constant offset removed, population variance."""
    data = np.asarray(data, dtype=np.float64)
    if data.ndim != 2 or data.shape[0] < 8 or not np.isfinite(data).all():
        raise ValueError("At least eight finite samples per channel are required")
    if not math.isfinite(dt) or dt <= 0:
        raise ValueError("Invalid sample interval")
    nperseg = min(4096, len(data))
    resolution = 1 / (dt * nperseg)
    if not (
        math.isfinite(low)
        and math.isfinite(high)
        and resolution <= low < high <= 0.5 / dt
    ):
        raise ValueError(
            f"Band must satisfy {resolution:.3g} ≤ low < high ≤ {0.5 / dt:.3g} Hz"
        )
    if high - low < resolution:
        raise ValueError(f"Band must be at least {resolution:.3g} Hz wide")
    ac = data - data.mean(axis=0)
    variance = np.mean(ac * ac, axis=0)
    frequency, power = welch(ac, fs=1 / dt, nperseg=nperseg, detrend="constant", axis=0)
    # Interpolate PSD at exact requested band edges before trapezoidal integration.
    inside = (frequency > low) & (frequency < high)

    def edge(value):
        j = int(np.searchsorted(frequency, value))
        j = min(max(j, 1), len(frequency) - 1)
        fraction = (value - frequency[j - 1]) / (frequency[j] - frequency[j - 1])
        return power[j - 1] + fraction * (power[j] - power[j - 1])

    band_frequency = np.r_[low, frequency[inside], high]
    band_power = np.vstack([edge(low), power[inside], edge(high)])
    return {
        "ac_rms": np.sqrt(variance),
        "variance": variance,
        "peak": np.max(np.abs(ac), axis=0),
        "band_rms": np.sqrt(
            np.maximum(0, np.trapezoid(band_power, band_frequency, axis=0))
        ),
        "resolution_hz": resolution,
    }


def frame_bounds(recording, frame):
    width = max(1, round(WINDOW_SECONDS / recording["dt"]))
    count = math.ceil(recording["samples"] / width)
    if frame < 0 or frame >= count:
        raise ValueError("Frame is outside this recording")
    a, b = frame * width, min((frame + 1) * width, recording["samples"])
    if b - a < 8:
        raise ValueError("Incomplete frame has fewer than eight samples")
    return a, b, width, count


def metric_frame(recording, frame=0, low=1.0, high=10.0):
    path = safe_path(recording["relative_path"])
    stat = path.stat()
    if (stat.st_size, stat.st_mtime_ns) != (
        recording["size_bytes"],
        recording["mtime_ns"],
    ):
        raise ValueError("Recording has changed; re-index before review")
    a, b, width, count = frame_bounds(recording, frame)
    if b - a > 2_000_000:
        raise ValueError("Frame exceeds the two-million-sample processing budget")
    key = hashlib.sha256(
        json.dumps(
            [
                VERSION,
                str(path),
                stat.st_size,
                stat.st_mtime_ns,
                recording["dt"],
                recording["scale"],
                recording["channels"],
                frame,
                low,
                high,
            ]
        ).encode()
    ).hexdigest()
    directory = Path(os.getenv("DAS_METRIC_CACHE", ROOT / ".local/metric-cache"))
    directory.mkdir(parents=True, exist_ok=True)
    cache = directory / (key + ".npz")
    with _calculation_lock:
        if not cache.is_file():
            output = {name: np.empty(len(recording["channels"])) for name in METRICS}
            with h5py.File(path, "r") as f:
                dataset = f["data"]
                # Bound raw-frame memory; larger budgets avoid repeated remote reads.
                read_mb = int(os.getenv("DAS_METRIC_READ_MB", "256"))
                if not 16 <= read_mb <= 1024:
                    raise ValueError("DAS_METRIC_READ_MB must be from 16 to 1024")
                raw = (
                    dataset[a:b, :]
                    if (b - a) * dataset.shape[1] * dataset.dtype.itemsize
                    <= read_mb * 1024**2
                    else None
                )
                block_width = max(1, min(128, 4_000_000 // (b - a)))
                for c in range(0, dataset.shape[1], block_width):
                    block = (
                        np.asarray(
                            raw[:, c : c + block_width]
                            if raw is not None
                            else dataset[a:b, c : c + block_width],
                            dtype=np.float64,
                        )
                        * recording["scale"]
                    )
                    computed = calculate_metrics(block, recording["dt"], low, high)
                    for name in METRICS:
                        output[name][c : c + block_width] = computed[name]
            after = path.stat()
            if (after.st_size, after.st_mtime_ns) != (stat.st_size, stat.st_mtime_ns):
                raise ValueError("Recording changed during calculation")
            with tempfile.NamedTemporaryFile(
                dir=directory, suffix=".npz", delete=False
            ) as tmp:
                np.savez_compressed(
                    tmp, **output, resolution_hz=computed["resolution_hz"]
                )
                tmpname = tmp.name
            os.replace(tmpname, cache)
        with np.load(cache, allow_pickle=False) as stored:
            values = {name: stored[name].copy() for name in METRICS}
            resolution = float(stored["resolution_hz"])
    return {
        "values": values,
        "frame": frame,
        "frame_count": count,
        "start_sample": a,
        "stop_sample": b,
        "start": a * recording["dt"],
        "end": b * recording["dt"],
        "actual_duration": (b - a) * recording["dt"],
        "complete": b - a == width,
        "nominal_duration": WINDOW_SECONDS,
        "resolution_hz": resolution,
        "processing": VERSION,
        "band": [low, high],
    }


def fibre_positions(lid):
    positions = rows(
        "SELECT channel,lid,latitude,longitude,gid,distance FROM masteliste WHERE lid=%s ORDER BY channel",
        (lid,),
    )
    if not positions:
        raise ValueError("Instrument has no masteliste positions")
    previous = None
    for p in positions:
        # masteliste's stored spatial grid is four native interrogator channels.
        if previous is None or p["channel"] - previous != MAPPING_CHANNEL_STEP:
            run = p["channel"]
        p["run"] = f"{lid}:{run}"
        previous = p["channel"]
    return positions


def geographic_distance(a, b):
    lat1, lat2 = math.radians(a["latitude"]), math.radians(b["latitude"])
    dlat = lat2 - lat1
    dlon = math.radians(b["longitude"] - a["longitude"])
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 2 * 6371008.8 * math.asin(math.sqrt(min(1, max(0, h))))


def interpolation_regions(recording, positions):
    """Prove a shared native channel origin from acquisition and mapping distances.

    Only regions whose first three mapping distances agree with the HDF5 native
    spacing are eligible. This is coordinate interpolation, never a signal shift.
    """
    with h5py.File(safe_path(recording["relative_path"]), "r") as f:
        required = [
            "demodSpec/roiStart",
            "demodSpec/roiEnd",
            "demodSpec/roiDec",
            "cableSpec/sensorDistances",
        ]
        if not all(k in f for k in required):
            return []
        channels = np.asarray(recording["channels"])
        if len(channels) < 2:
            return []
        distances = np.asarray(f["cableSpec/sensorDistances"][: min(10, len(channels))])
        steps = np.diff(channels[: len(distances)])
        if not len(steps) or np.any(steps <= 0):
            return []
        spacing = float(np.median(np.diff(distances) / steps))
        if not math.isfinite(spacing) or spacing <= 0:
            return []
        regions = []
        for start, end, step in zip(
            f[required[0]][()], f[required[1]][()], f[required[2]][()]
        ):
            start, end, step = int(start), int(end), int(step)
            anchors = [p for p in positions if start <= p["channel"] <= end][:3]
            if (len(anchors) != 3 or step <= 0 or step % MAPPING_CHANNEL_STEP
                    or anchors[0]["channel"] - start >= MAPPING_CHANNEL_STEP):
                continue
            if all(
                p["distance"] is not None
                and abs(p["distance"] - (p["channel"] - start) * spacing) < 0.05
                for p in anchors
            ):
                regions.append(
                    {
                        "start": start,
                        "end": end,
                        "step": MAPPING_CHANNEL_STEP,
                        "acquisition_step": step,
                        "native_spacing_m": spacing,
                        "evidence": "First three masteliste distances agree with HDF5 native spacing and ROI origin within 0.05 m",
                    }
                )
        return regions


def resolve_positions(recording, positions, regions):
    keys = [p["channel"] for p in positions]
    indexed = {p["channel"]: p for p in positions}
    result = []
    counts = {"exact": 0, "interpolated": 0, "outside": 0, "gap": 0, "unresolved": 0}
    for channel in recording["channels"]:
        if channel in indexed:
            result.append(
                dict(
                    **indexed[channel],
                    recording_channel=channel,
                    mapped_channel=channel,
                    mapping="exact",
                    lower_channel=channel,
                    upper_channel=channel,
                )
            )
            counts["exact"] += 1
            continue
        region = next((r for r in regions if r["start"] <= channel <= r["end"]), None)
        if region is None:
            counts["unresolved"] += 1
            continue
        j = bisect.bisect_left(keys, channel)
        if j == 0 or j == len(keys):
            counts["outside"] += 1
            continue
        a, b = positions[j - 1], positions[j]
        if a["channel"] < region["start"] or b["channel"] > region["end"]:
            counts["outside"] += 1
            continue
        if (
            b["channel"] - a["channel"] != region["step"]
            or a["run"] != b["run"]
            or geographic_distance(a, b)
            > 2 * region["step"] * region["native_spacing_m"] + 1
        ):
            counts["gap"] += 1
            continue
        fraction = (channel - a["channel"]) / (b["channel"] - a["channel"])
        result.append(
            {
                "channel": channel,
                "lid": a["lid"],
                "run": a["run"],
                "latitude": a["latitude"] + fraction * (b["latitude"] - a["latitude"]),
                "longitude": a["longitude"]
                + fraction * (b["longitude"] - a["longitude"]),
                "gid": a["gid"] if a["gid"] == b["gid"] else None,
                "recording_channel": channel,
                "mapped_channel": None,
                "mapping": "interpolated",
                "lower_channel": a["channel"],
                "upper_channel": b["channel"],
            }
        )
        counts["interpolated"] += 1
    return result, counts


def map_metrics(recording, lid, frame=0, metric="ac_rms", low=1.0, high=10.0, illustrative=False):
    if metric not in METRICS:
        raise ValueError("Unknown signal metric")
    if recording["lid"] is not None and recording["lid"] != lid:
        raise ValueError("Selected instrument does not match the recording")
    result = metric_frame(recording, frame, low, high)
    positions = fibre_positions(lid)
    regions = interpolation_regions(recording, positions)
    resolved, counts = resolve_positions(recording, positions, regions)
    columns = {channel: i for i, channel in enumerate(recording["channels"])}
    # Derive display adjacency from the full recording, before geographic filtering.
    # The minimum is conservative for mixed decimation: larger gaps never merge.
    deltas = np.diff(sorted(columns))
    channel_step = int(deltas.min()) if len(deltas) else None
    features = [
        {
            "type": "Feature",
            "id": p["recording_channel"],
            "geometry": {
                "type": "Point",
                "coordinates": [p["longitude"], p["latitude"]],
            },
            "properties": dict(
                **p,
                channel_step=channel_step,
                value=float(result["values"][metric][columns[p["recording_channel"]]]),
            ),
        }
        for p in resolved
    ]
    values = [f["properties"]["value"] for f in features]
    missing = len(columns) - len(features)
    source_frame = dict(result)
    result.pop("values")
    output = dict(
        **result,
        recording_id=recording["id"],
        lid=lid,
        metric=metric,
        unit=f"({recording['unit']})²" if metric == "variance" else recording["unit"],
        acquisition_epoch=recording["acquisition_epoch"],
        time_verified=recording["time_verified"],
        data={"type": "FeatureCollection", "features": features},
        scale={"min": 0, "max": float(np.percentile(values, 99)) if values else 1},
        mapping=dict(
            status="partial" if missing else "mapped",
            matched=len(features),
            recording_channels=len(columns),
            unmatched_recording=missing,
            **counts,
            regions=regions,
            note="masteliste geometry: exact IDs or interpolation within adjacent samples with a matching acquisition origin; no extrapolation, gap bridging or signal-channel shift.",
        ),
    )

    from .calm import add_map_normalization
    add_map_normalization(output, recording, source_frame, metric, illustrative)
    return output
