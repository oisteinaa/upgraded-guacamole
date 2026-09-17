"""Bounded display summaries; explicit channel IDs, never spatial interpolation."""

import math

import h5py
import numpy as np

from .signals import safe_path


def channel_groups(channels, limit=300):
    """Contiguous bins plus explicit gap bins, retaining original column indices."""
    ids = np.asarray(channels, dtype=np.int64)
    order = np.argsort(ids)
    ordered = ids[order]
    differences = np.diff(ordered)
    if len(ids) == 0 or np.any(differences <= 0):
        raise ValueError("Channels must be nonempty and unique")
    step = int(differences.min()) if len(differences) else 1
    runs = np.split(order, np.flatnonzero(differences > step) + 1)
    if 2 * len(runs) - 1 > limit:
        raise ValueError("Too many channel gaps for the bounded live summary")
    width = max(1, math.ceil(len(ids) / (limit - len(runs) + 1)))
    while sum(math.ceil(len(run) / width) for run in runs) + len(runs) - 1 > limit:
        width += 1
    groups, edges = [], [float(ordered[0] - step / 2)]
    for i, run in enumerate(runs):
        if i:
            groups.append(None)
            edges.append(float(ids[run[0]] - step / 2))
        for start in range(0, len(run), width):
            group = run[start:start + width]
            groups.append(group)
            edges.append(float(ids[group[-1]] + step / 2))
    return groups, edges


def profile_summary(channels, values):
    groups, _ = channel_groups(channels, 600)
    x, y = [], []
    for group in groups:
        if group is None:
            x.append(None)
            y.append(None)
            continue
        selected = sorted({int(group[np.argmin(values[group])]),
                           int(group[np.argmax(values[group])])}, key=lambda i: channels[i])
        for i in selected:
            x.append(int(channels[i]))
            y.append(float(values[i]))
    return {"channels": x, "values": y}


def recording_summary(recording):
    """One streamed read produces whole-file raw RMS and a time-binned AC view."""
    path = safe_path(recording["relative_path"])
    identity = (recording["size_bytes"], recording["mtime_ns"])
    if (path.stat().st_size, path.stat().st_mtime_ns) != identity:
        raise ValueError("Recording has changed; re-index before capture")
    n, count = len(recording["channels"]), recording["samples"]
    if not 0 < n <= 1_000_000 or count < 8:
        raise ValueError("Recording exceeds live channel budget or has too few samples")
    # Excessively fragmented inputs still support capture and detection.
    try:
        groups, edges = channel_groups(recording["channels"])
        heat_error = None
    except ValueError as exc:
        groups, edges, heat_error = [], [], str(exc)
    bounds = np.linspace(0, count, min(120, count // 8) + 1, dtype=int)
    sums, squares = np.zeros(n), np.zeros(n)
    heat, peak_channels = [], []
    block_rows = max(1, min(256, 1_000_000 // n))
    with h5py.File(path, "r") as f:
        if f["data"].shape != (count, n):
            raise ValueError("Recording shape changed")
        if "header/missingSamples" not in f or f["header/missingSamples"].size:
            raise ValueError("Recording declares missing samples")
        for start, stop in zip(bounds[:-1], bounds[1:]):
            local_sum, local_sq, offset = np.zeros(n), np.zeros(n), None
            for a in range(int(start), int(stop), block_rows):
                block = np.asarray(f["data"][a:min(a + block_rows, stop), :], dtype=np.float64)
                block *= recording["scale"]
                if not np.all(np.isfinite(block)):
                    raise ValueError("Nonfinite samples in live recording")
                sums += block.sum(axis=0)
                squares += np.einsum("ij,ij->j", block, block)
                if offset is None:
                    offset = block[0].copy()
                block -= offset
                local_sum += block.sum(axis=0)
                local_sq += np.einsum("ij,ij->j", block, block)
            ac = np.sqrt(np.maximum(0, local_sq / (stop - start) - (local_sum / (stop - start)) ** 2))
            row, peaks = [], []
            for group in groups:
                if group is None:
                    row.append(None)
                    peaks.append(None)
                else:
                    index = int(group[np.argmax(ac[group])])
                    row.append(float(ac[index]))
                    peaks.append(int(recording["channels"][index]))
            heat.append(row)
            peak_channels.append(peaks)
    if (path.stat().st_size, path.stat().st_mtime_ns) != identity:
        raise ValueError("Recording changed during capture")
    rms = np.sqrt(squares / count)
    variance = np.maximum(0, squares / count - (sums / count) ** 2)
    summary = {"status": "unavailable", "note": heat_error} if heat_error else {
        "status": "complete", "channel_edges": edges,
        "time_edges": (bounds * recording["dt"]).tolist(),
        "values": heat, "peak_channels": peak_channels,
        "aggregation": "Maximum per-channel AC RMS in each time/channel bin",
    }
    return rms, variance, summary
