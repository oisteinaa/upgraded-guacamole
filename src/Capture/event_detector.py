"""Explicit, versioned RMS rules for scaled stored signals.

Old limits were derived from a different integration/unwrapping pipeline and
cannot be applied to phase-rate RMS. This detector requires calibrated rules.
Threshold candidates remain unclassified until reviewed.
"""

import math
from datetime import datetime
from zoneinfo import ZoneInfo

from src.Mapui.db import database


def detect_events(recording, rms_by_channel, rules, legacy_timezone):
    if (
        not recording["time_verified"]
        or not recording["mapping_verified"]
        or recording["lid"] is None
    ):
        raise ValueError(
            "Detection requires independently verified time and instrument/channel mapping"
        )
    zone = ZoneInfo(legacy_timezone)
    source_time = datetime.fromtimestamp(recording["acquisition_epoch"], zone).replace(
        tzinfo=None
    )
    candidates = []
    # Validate the whole rule set before any writes.
    for rule in rules:
        if (
            rule.get("processing") != recording["processing"]
            or rule.get("unit") != recording["unit"]
        ):
            raise ValueError("Rule unit/processing does not match the recording")
        limit = float(rule["rms_limit"])
        if not math.isfinite(limit) or limit <= 0:
            raise ValueError("Rule limit must be finite and positive")
        if not str(rule.get("name", "")).strip() or len(rule["name"]) > 80:
            raise ValueError("Rule name must be 1–80 characters")
        if rule["lid"] != recording["lid"]:
            continue
        for channel in rule["channels"]:
            value = rms_by_channel.get(channel)
            if value is not None and value > limit:
                candidates.append((rule, channel, value))
    created = []
    with database(write=True) as cur:
        # Serialize each recording's detection and make replay/retries idempotent.
        cur.execute(
            "SELECT id FROM das_recordings WHERE id=%s FOR UPDATE", (recording["id"],)
        )
        for rule, channel, value in candidates:
            cur.execute(
                "SELECT 1 FROM masteliste WHERE lid=%s AND channel=%s",
                (recording["lid"], channel),
            )
            if not cur.fetchone():
                raise ValueError(
                    f"Channel {channel} has no exact mapping; cannot localize a candidate"
                )
            cur.execute(
                "SELECT 1 FROM event_context WHERE recording_id=%s AND channel=%s",
                (recording["id"], channel),
            )
            if cur.fetchone():
                continue
            cur.execute(
                "INSERT INTO events(time,type,value,comment) VALUES (%s,1,%s,%s) RETURNING id",
                (source_time, value, rule["name"]),
            )
            event_id = cur.fetchone()["id"]
            cur.execute(
                """INSERT INTO event_context(event_id,recording_id,start_sample,stop_sample,lid,channel,route,alignment_verified,evidence)
                           VALUES (%s,%s,0,%s,%s,%s,%s,true,%s)""",
                (
                    event_id,
                    recording["id"],
                    recording["samples"],
                    recording["lid"],
                    channel,
                    rule.get("route"),
                    f"RMS candidate: {value:g} > {rule['rms_limit']} {recording['unit']}; {recording['processing']}; legacy timezone {legacy_timezone}",
                ),
            )
            created.append(event_id)
    return created
