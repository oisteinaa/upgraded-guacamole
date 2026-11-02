"""Bounded acquisition-time history stored atomically with the live snapshot."""
import hashlib
import json
import math

import numpy as np

WINDOW_SECONDS = 15 * 60
MAX_ROWS = 92


def recording_history(recording, illustrative=False):
    from .calm import fingerprint, normalize_frame, reference
    from .live_summary import channel_groups
    from .metrics import frame_bounds, metric_frame

    groups, edges = channel_groups(recording['channels'])
    ref = reference(recording, illustrative)
    identity = [recording.get('lid'), fingerprint(recording), ref[0].get('baseline_id'), illustrative]
    key = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    _, _, width, count = frame_bounds(recording, 0)
    rows = []
    for index in range(max(0, count - MAX_ROWS), count):
        if min(width, recording['samples'] - index * width) < 8:
            continue
        frame = metric_frame(recording, index)
        if not frame['complete']:
            continue
        values = frame['values']['ac_rms']
        _, scores = normalize_frame(recording, frame, ref=ref, illustrative=illustrative)
        row = dict(start=recording['acquisition_epoch'] + frame['start'],
                   end=recording['acquisition_epoch'] + frame['end'],
                   recording_id=recording['id'], raw=[], raw_channels=[],
                   calm=[], calm_channels=[], calm_raw=[], medians=[])
        for group in groups:
            raw = None if group is None else int(group[np.argmax(values[group])])
            valid = [] if group is None else [int(i) for i in group if np.isfinite(scores[i])]
            calm = max(valid, key=lambda i: scores[i]) if valid else None
            row['raw'].append(float(values[raw]) if raw is not None else None)
            row['raw_channels'].append(recording['channels'][raw] if raw is not None else None)
            row['calm'].append(float(scores[calm]) if calm is not None else None)
            row['calm_channels'].append(recording['channels'][calm] if calm is not None else None)
            row['calm_raw'].append(float(values[calm]) if calm is not None else None)
            row['medians'].append(float(ref[1]['ac_rms_median'][calm]) if calm is not None else None)
        rows.append(row)
    return dict(key=key, channel_edges=edges, rows=rows, window_seconds=WINDOW_SECONDS,
                sample_interval=recording['dt'], unit=recording['unit'])


def merge_history(previous, incoming):
    """Idempotent updates, bounded rows and explicit gaps; never stretch a frame."""
    compatible = (previous and previous.get('key') == incoming['key']
                  and previous.get('channel_edges') == incoming['channel_edges'])
    existing = previous.get('rows', []) if compatible else []
    indexed = {(r['start'], r['end']): r for r in existing}
    indexed.update({(r['start'], r['end']): r for r in incoming['rows']})
    ordered = sorted(indexed.values(), key=lambda r: r['start'])
    if not ordered:
        return dict(incoming, rows=[])
    latest = max(r['end'] for r in ordered)
    kept = []
    for row in ordered:
        if row['end'] <= latest - WINDOW_SECONDS:
            continue
        # Reject conflicting overlapping frames rather than draw overlapping cells.
        if kept and row['start'] < kept[-1]['end'] - max(1e-6, incoming['sample_interval']):
            continue
        if not (math.isfinite(row['start']) and math.isfinite(row['end']) and row['end'] > row['start']):
            continue
        kept.append(row)
    return dict(incoming, rows=kept[-MAX_ROWS:])
