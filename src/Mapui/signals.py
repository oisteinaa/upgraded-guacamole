"""Bounded HDF5 reads. Display reduction never feeds spectral estimates."""

import math
import os
from pathlib import Path

import h5py
import numpy as np
from scipy.signal import welch

from .db import ROOT, database


def archive_root():
    return Path(os.getenv("DAS_ARCHIVE_ROOT", ROOT / ".local/recordings")).resolve()


def safe_path(relative):
    root = archive_root()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("Recording is unavailable in the configured archive")
    return path


def inspect_recording(path):
    path = Path(path).resolve()
    relative = str(path.relative_to(archive_root()))
    before = path.stat()
    with h5py.File(path, "r") as f:
        data = f["data"]
        if data.ndim != 2 or min(data.shape) < 1 or data.dtype.kind not in "iuf":
            raise ValueError("Expected a numeric samples × channels dataset")
        channels = np.asarray(f["header/channels"][()])
        if (
            channels.ndim != 1
            or len(channels) != data.shape[1]
            or channels.dtype.kind not in "iu"
            or len(np.unique(channels)) != len(channels)
        ):
            raise ValueError("Header must contain one unique integer ID per channel")
        dt, start, scale = (
            float(f["header/" + key][()]) for key in ["dt", "time", "dataScale"]
        )
        if (
            not all(math.isfinite(x) for x in [dt, start, scale])
            or dt <= 0
            or scale == 0
        ):
            raise ValueError("Invalid acquisition timing or scaling")
        if "header/missingSamples" not in f or f["header/missingSamples"].size:
            raise ValueError(
                "Missing-sample metadata absent or samples missing; review required"
            )
        unit = f["header/unit"][()]
        unit = unit.decode() if isinstance(unit, bytes) else str(unit)
        result = {
            "relative_path": relative,
            "acquisition_epoch": start,
            "dt": dt,
            "samples": data.shape[0],
            "channels": channels.tolist(),
            "unit": unit,
            "scale": scale,
            "size_bytes": before.st_size,
            "mtime_ns": before.st_mtime_ns,
        }
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Recording changed during inspection")
    return result


def register_recording(path, lid=None, time_verified=False, mapping_verified=False):
    if mapping_verified and lid is None:
        raise ValueError("A verified instrument mapping requires a lid")
    item = inspect_recording(path)
    item.update(lid=lid, time_verified=time_verified, mapping_verified=mapping_verified)
    with database(write=True) as cur:
        # Changed files invalidate explicit event alignment instead of silently retargeting it.
        cur.execute(
            "SELECT id, size_bytes, mtime_ns, time_verified, mapping_verified FROM das_recordings WHERE relative_path=%s FOR UPDATE",
            (item["relative_path"],),
        )
        old = cur.fetchone()
        if old and (
            (old["size_bytes"], old["mtime_ns"])
            != (item["size_bytes"], item["mtime_ns"])
            or old["time_verified"]
            and not time_verified
            or old["mapping_verified"]
            and not mapping_verified
        ):
            cur.execute(
                "UPDATE event_context SET alignment_verified=false WHERE recording_id=%s",
                (old["id"],),
            )
        cur.execute(
            """INSERT INTO das_recordings
            (relative_path,acquisition_epoch,dt,samples,channels,unit,scale,size_bytes,mtime_ns,lid,time_verified,mapping_verified)
            VALUES (%(relative_path)s,%(acquisition_epoch)s,%(dt)s,%(samples)s,%(channels)s,%(unit)s,%(scale)s,%(size_bytes)s,%(mtime_ns)s,%(lid)s,%(time_verified)s,%(mapping_verified)s)
            ON CONFLICT (relative_path) DO UPDATE SET acquisition_epoch=EXCLUDED.acquisition_epoch,
            dt=EXCLUDED.dt,samples=EXCLUDED.samples,channels=EXCLUDED.channels,unit=EXCLUDED.unit,
            scale=EXCLUDED.scale,size_bytes=EXCLUDED.size_bytes,mtime_ns=EXCLUDED.mtime_ns,
            lid=EXCLUDED.lid,time_verified=EXCLUDED.time_verified,mapping_verified=EXCLUDED.mapping_verified,
            indexed_at=CURRENT_TIMESTAMP RETURNING id""",
            item,
        )
        return cur.fetchone()["id"]


def envelope(values, start_sample, dt, budget=1600):
    """Retain actual extrema in temporal order, including a short final bucket."""
    width = max(1, math.ceil(len(values) / max(1, budget // 2)))
    indices = []
    for a in range(0, len(values), width):
        chunk = values[a : a + width]
        indices.extend(sorted({a + int(np.argmin(chunk)), a + int(np.argmax(chunk))}))
    indices = np.asarray(indices)
    return ((indices + start_sample) * dt).tolist(), values[indices].tolist()


def read_signal(recording, channel, start, duration, points=1600, neighbors=16, channel_count=None, channel_bounds=None):
    path = safe_path(recording["relative_path"])
    stat = path.stat()
    if (stat.st_size, stat.st_mtime_ns) != (
        recording["size_bytes"],
        recording["mtime_ns"],
    ):
        raise ValueError("Recording has changed; re-index before review")
    channels = recording["channels"]
    bounds = channel_bounds
    if channel_count is not None:
        if channel_count < 1:
            raise ValueError("Number of channels must be positive")
        bounds = (channel - channel_count / 2, channel + channel_count / 2)
    if bounds is not None:
        selected = sorted((i for i, c in enumerate(channels) if bounds[0] <= c <= bounds[1]))
        if not selected:
            raise ValueError("No recorded channels inside the selected range")
        channel = min((channels[i] for i in selected), key=lambda c: (abs(c - channel), c))
    if channel not in channels:
        raise ValueError("Channel ID is not present in this recording")
    dt, total = recording["dt"], recording["samples"]
    a, b = max(0, int(start / dt)), min(total, math.ceil((start + duration) / dt))
    if b - a < 8:
        raise ValueError(
            "Select a window with at least eight samples inside the recording"
        )
    if b - a > 2_000_000:
        raise ValueError(
            "Window exceeds two million samples; select a shorter interval"
        )
    column = channels.index(channel)
    # Never assume successive column IDs imply geographic adjacency. Preserve each ID.
    lo = max(0, column - neighbors // 2)
    hi = min(len(channels), lo + neighbors)
    if bounds is None:
        selected = list(range(lo, hi))
    if len(selected) * (b - a) > 50_000_000:
        raise ValueError("Channel range exceeds 50 million values; select fewer channels or a shorter interval")
    bucket = max(1, math.ceil((b - a) / 400))
    heat, rms, variance, times = [], [], [], []
    heat_times = []
    channel_variance = []
    with h5py.File(path, "r") as f:
        wave = np.asarray(f["data"][a:b, column], dtype=np.float64) * recording["scale"]
        if not np.all(np.isfinite(wave)):
            raise ValueError("Recording contains nonfinite samples")
        for s in range(a, b, bucket):
            data = (
                np.asarray(f["data"][s : min(s + bucket, b), selected], dtype=np.float64)
                * recording["scale"]
            )
            if not np.all(np.isfinite(data)):
                raise ValueError("Recording contains nonfinite samples")
            heat.append(np.sqrt(np.mean(data * data, axis=0)).tolist())
            heat_times.append((s + (len(data) - 1) / 2) * dt)
        frame_samples = max(1, round(10 / dt))
        analysis_start = (a // frame_samples) * frame_samples
        analysis_stop = min(total, math.ceil(b / frame_samples) * frame_samples)
        if len(selected) * (analysis_stop - analysis_start) > 50_000_000:
            raise ValueError("Analysis exceeds 50 million values; select fewer channels or a shorter interval")
        for frame_start in range(
            (a // frame_samples) * frame_samples, b, frame_samples
        ):
            stop = min(total, frame_start + frame_samples)
            chunk = (
                np.asarray(f["data"][frame_start:stop, column], dtype=np.float64)
                * recording["scale"]
            )
            if not np.isfinite(chunk).all():
                raise ValueError("Recording contains nonfinite samples")
            # Population variance per recorded channel, retaining the fixed analysis frames.
            spatial = np.asarray(f["data"][frame_start:stop, selected], dtype=np.float64) * recording["scale"]
            if not np.isfinite(spatial).all():
                raise ValueError("Recording contains nonfinite samples")
            channel_variance.append(np.var(spatial, axis=0).tolist())
            v = float(np.var(chunk))
            rms.append(math.sqrt(v))
            variance.append(v)
            times.append((frame_start + (len(chunk) - 1) / 2) * dt)
    x, y = envelope(wave, a, dt, points)
    freq, power = welch(wave, fs=1 / dt, nperseg=min(len(wave), 4096), detrend="linear")
    # Spectrum display only: preserve maximum power per frequency bucket.
    sx, sy = [], []
    stride = max(1, math.ceil(len(freq) / 1000))
    for i in range(0, len(freq), stride):
        peak = i + int(np.argmax(power[i : i + stride]))
        sx.append(float(freq[peak]))
        sy.append(float(power[peak]))
    return {
        "recording_id": recording["id"],
        "channel": channel,
        "unit": recording["unit"],
        "processing": recording["processing"],
        "time_verified": recording["time_verified"],
        "start": a * dt,
        "end": b * dt,
        "duration": total * dt,
        "sample_rate": 1 / dt,
        "acquisition_epoch": recording["acquisition_epoch"],
        "source_samples": b - a,
        "display_points": len(x),
        "x": x,
        "y": y,
        "trend_time": times,
        "rms": rms,
        "variance": variance,
        "channel_variance": channel_variance,
        "channel_rms": np.sqrt(channel_variance).tolist(),
        "trend_start": analysis_start * dt,
        "heat_time": heat_times,
        "trend_window_seconds": frame_samples * dt,
        "heat_channels": [channels[i] for i in selected],
        "channel_bounds": list(bounds) if bounds is not None else None,
        "heat": np.asarray(heat).T.tolist(),
        "frequency": sx,
        "power": sy,
    }
