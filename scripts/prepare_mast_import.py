#!/usr/bin/env python3
"""Prepare the four-route mast migration offline; never connects to the database.

Requires Python 3, openpyxl, numpy and pyproj. See docs/masts.md for inputs
and the explicit route-order and water-screening assumptions.
"""
import argparse
import csv
import hashlib
import io
import json
import re
from pathlib import Path

import numpy as np
import openpyxl
from pyproj import Geod, Transformer


EXPECTED = {"R06": 188, "R12": 94, "R13": 101, "R14": 196}
# Visually reviewed candidates from Kartverket topo maps, 2026-09-16.
# This is not an exhaustive water inventory or evidence of submerged cable.
WATER_CANDIDATES = {
    ("R06", "M11", "M12"), ("R06", "M12", "M13"),
    ("R06", "M19", "M20"), ("R06", "M44", "M45"),
    ("R06", "M86", "M87"), ("R06", "M177", "M178"),
    ("R12", "M82", "M83"),
}
GEOD = Geod(ellps="WGS84")


def label_key(label):
    match = re.fullmatch(r"M(\d+)([A-Z]*)", label)
    if match is None:
        raise ValueError(f"Unexpected mast label: {label}")
    return int(match[1]), match[2]


def read_masts(directory, snapshot):
    channels = sorted(snapshot["channels"], key=lambda c: (c["lid"], c["channel"]))
    if not channels or {c["lid"] for c in channels} != {1}:
        raise ValueError("This import requires the inspected single DAS line (lid=1)")
    lon = np.array([c["longitude"] for c in channels], dtype=float)
    lat = np.array([c["latitude"] for c in channels], dtype=float)
    if not np.all(np.isfinite(lon)) or not np.all(np.isfinite(lat)):
        raise ValueError("Invalid channel coordinates")
    transform = Transformer.from_crs(32633, 4326, always_xy=True)
    result = []
    seen_routes = set()
    for path in sorted(directory.glob("*.xlsx")):
        route = re.search(r"R\d+", path.name)[0]
        if route not in EXPECTED or route in seen_routes:
            raise ValueError(f"Unexpected or duplicate route: {route}")
        seen_routes.add(route)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
        sheet = workbook.worksheets[0]
        values = list(sheet.values)
        if values[0][4] != "Driftsmerking" or values[0][9:11] != ("Geografisk øst", "Geografisk nord"):
            raise ValueError(f"Unexpected columns in {path}")
        rows = []
        for source_row, r in enumerate(values[2:], 3):
            if not any(v is not None for v in r):
                continue
            mast = "M" + re.sub(r"^0+(?=\d)", "", str(r[4]).strip().upper())
            label_key(mast)
            x, y = float(r[9]), float(r[10])
            longitude, latitude = transform.transform(x, y, errcheck=True)
            if not (67 < latitude < 69 and 12 < longitude < 16):
                raise ValueError(f"Coordinate outside expected route area: {route} {mast}")
            distances = GEOD.inv(np.full(len(channels), longitude),
                                 np.full(len(channels), latitude), lon, lat)[2]
            idx = int(np.argmin(distances))
            channel = channels[idx]
            if distances[idx] > 600:
                raise ValueError(f"Unexpectedly distant channel: {route} {mast}")
            rows.append(dict(route=route, mast=mast, object_number=int(r[1]),
                             route_name=r[2], mast_type=r[3] or "", voltage_kv=r[5],
                             owner=r[8] or "", utmx=x, utmy=y,
                             latitude=latitude, longitude=longitude, lid=channel["lid"],
                             channel=channel["channel"], channel_distance_m=float(distances[idx]),
                             source_file=path.name, source_sheet=sheet.title,
                             source_row=source_row, source_sha256=digest))
        workbook.close()
        if len(rows) != EXPECTED[route] or len({r["mast"] for r in rows}) != len(rows):
            raise ValueError(f"Unexpected count or duplicate labels in {route}")
        # R14's lettered replacement masts do not follow numeric order.
        # Geography and the full channel mapping support descending channel order.
        rows.sort(key=(lambda r: -r["channel"]) if route == "R14"
                  else (lambda r: label_key(r["mast"])))
        for pos, row in enumerate(rows, 1):
            row["route_position"] = pos
        result.extend(rows)
    if seen_routes != set(EXPECTED):
        raise ValueError("Not all four source routes were found")
    if len({r["object_number"] for r in result}) != len(result):
        raise ValueError("Duplicate source object numbers")
    old = snapshot["masts"]
    if len(old) != 188 or {r["mast"] for r in old} != {f"M{i}" for i in range(1, 189)}:
        raise ValueError("Expected the original 188 R06 masts")
    old_by_label = {r["mast"]: r for r in old}
    next_id = max(r["id"] for r in old) + 1
    for row in result:
        if row["route"] == "R06":
            previous = old_by_label[row["mast"]]
            if abs(row["utmx"] - previous["utmx"]) > .01 or abs(row["utmy"] - previous["utmy"]) > .01:
                raise ValueError("R06 spreadsheet differs from CSV by more than rounding")
            row["id"] = previous["id"]
        else:
            row["id"] = next_id
            next_id += 1
    return result


def build_spans(rows):
    spans = []
    for route in EXPECTED:
        route_rows = sorted((r for r in rows if r["route"] == route), key=lambda r: r["route_position"])
        for pos, (a, b) in enumerate(zip(route_rows, route_rows[1:]), 1):
            length = GEOD.inv(a["longitude"], a["latitude"], b["longitude"], b["latitude"])[2]
            reasons = []
            if label_key(b["mast"])[0] - label_key(a["mast"])[0] != 1:
                reasons.append("Nonconsecutive mast numbering; connection inferred, not verified")
            if max(a["channel_distance_m"], b["channel_distance_m"]) > 10:
                reasons.append("Endpoint farther than 10 m from nearest mapped channel")
            if length > 1000:
                reasons.append("Long endpoint connection; actual cable path and placement unknown")
            candidate = (route, a["mast"], b["mast"]) in WATER_CANDIDATES
            spans.append(dict(id=len(spans)+1, route=route, span_order=pos,
                              from_mast_id=a["id"], to_mast_id=b["id"],
                              from_mast=a["mast"], to_mast=b["mast"], straight_length_m=length,
                              connection_basis="channel_order_and_geography" if route == "R14" else "mast_number_order",
                              connection_status="inferred", review_reason="; ".join(reasons),
                              water_status="map_candidate" if candidate else "unknown",
                              water_source="Kartverket Topografisk Norgeskart WMS; visual map screening 2026-09-16" if candidate else "",
                              installation="unknown"))
    if len(spans) != 575 or sum(s["water_status"] == "map_candidate" for s in spans) != len(WATER_CANDIDATES):
        raise ValueError("Unexpected span or water-candidate count")
    return spans


def copy_sql(table, rows, fields):
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    for row in rows:
        writer.writerow([row[key] for key in fields])
    return f"COPY {table} ({','.join(fields)}) FROM stdin WITH CSV;\n" + buffer.getvalue() + "\\.\n"


def write_csv(path, rows):
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--output", type=Path, default=Path("migrations/003_mast_routes_spans.sql"))
    parser.add_argument("--audit-dir", type=Path, default=Path("results/masts"))
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text())
    rows = read_masts(args.source_dir, snapshot)
    spans = build_spans(rows)
    template = Path(__file__).with_name("mast_import_schema.sql").read_text()
    fields = ["id", "route", "mast", "object_number", "route_position", "utmx", "utmy", "latitude", "longitude", "lid", "channel", "channel_distance_m", "source_file", "source_sheet", "source_row", "source_sha256", "mast_type", "voltage_kv", "owner"]
    span_fields = [k for k in spans[0] if k not in ("from_mast", "to_mast")]
    # The original full snapshot prevents accidentally applying this once-only
    # migration to changed mast data. Channel coordinates are checked as well.
    old_fields = list(snapshot["masts"][0])
    expected_channels = []
    by_key = {(r["lid"], r["channel"]): r for r in snapshot["channels"]}
    for key in sorted({(r["lid"], r["channel"]) for r in rows}):
        expected_channels.append(by_key[key])
    sql = template.replace("-- INSERT_ORIGINAL_SNAPSHOT", copy_sql("_original_masts", snapshot["masts"], old_fields))
    sql = sql.replace("-- INSERT_CHANNEL_SNAPSHOT", copy_sql("_expected_channels", expected_channels, ["lid", "channel", "latitude", "longitude"]))
    sql = sql.replace("-- INSERT_MAST_ROWS", copy_sql("_mast_import", rows, fields))
    sql = sql.replace("-- INSERT_SPAN_ROWS", copy_sql("public.mast_spans", spans, span_fields))
    args.output.write_text(sql)
    args.audit_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.audit_dir / "masts.csv", rows)
    write_csv(args.audit_dir / "spans.csv", spans)
    write_csv(args.audit_dir / "water-candidates.csv", [s for s in spans if s["water_status"] == "map_candidate"])
    write_csv(args.audit_dir / "masts-before-import.csv", snapshot["masts"])
    print(f"Prepared {len(rows)} masts and {len(spans)} spans: {args.output}")
    for route in EXPECTED:
        distances = [r["channel_distance_m"] for r in rows if r["route"] == route]
        print(route, len(distances), "distance median/p95/max (m):", np.percentile(distances, [50, 95, 100]))


if __name__ == "__main__":
    main()
