"""Read-only archive/weather learning. Run: python -m src.Mapui.train_calm --activate."""
import argparse
import bisect
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

import numpy as np

from .calm import VERSION, artifact_root, fingerprint, robust_fit, score
from .db import rows
from .metrics import (METRICS, metric_frame, fibre_positions, interpolation_regions,
                      resolve_positions, geographic_distance)


def weather_at(items, target, max_age=7200):
    """Use only forecasts actually available by target; no legacy-time fallback."""
    index = bisect.bisect_right([r["valid"] for r in items], target)
    for row in reversed(items[:index]):
        if target - row["valid"] > max_age:
            break
        if row["issued"] <= target and row["collected"] <= target:
            return row
    return None


def split_calm(indices, epochs):
    hours = sorted({int(epochs[i] // 3600) for i in indices})
    hold = set(hours[-max(2, math.ceil(.2 * len(hours))):])
    train = [i for i in indices if int(epochs[i] // 3600) not in hold]
    test = [i for i in indices if int(epochs[i] // 3600) in hold]
    dates = {datetime.fromtimestamp(epochs[i], timezone.utc).date() for i in train}
    eligible = len(train) >= 120 and len({int(epochs[i] // 3600) for i in train}) >= 3 and len(dates) >= 2 and len(hold) >= 2 and bool(test)
    return train, test, eligible


def distribution(values):
    v = np.asarray(values)
    v = v[np.isfinite(v)]
    return {"count": int(v.size), "p50": float(np.percentile(v, 50)), "p95": float(np.percentile(v, 95)),
            "p99": float(np.percentile(v, 99)), "fraction_above_3": float(np.mean(v > 3)),
            "fraction_above_6": float(np.mean(v > 6))} if v.size else {"count": 0}


def atomic_json(path, data):
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as f:
        json.dump(data, f, allow_nan=False, indent=2)
        temporary = f.name
    os.replace(temporary, path)


def finalize_manifest(manifest):
    """Distinguish the requested search interval from actual fitting coverage."""
    manifest.setdefault("requested_start", manifest["training_start"])
    manifest.setdefault("requested_end", manifest["training_end"])
    fitted = []
    for config in manifest["configurations"].values():
        keys = {tuple(frame) for frame in config["fit_frames"]}
        fitted.extend(source["epoch"] for source in config["sources"] if (source["path"], source["frame"]) in keys)
    if fitted:
        manifest["training_start"] = min(fitted)
        manifest["training_end"] = max(fitted) + 10
    return manifest


def train(args):
    root = artifact_root()
    root.mkdir(parents=True, exist_ok=True)
    end = args.end or datetime.now(timezone.utc).timestamp()
    start = args.start or end - 30 * 86400
    # Never materialize channel arrays for the entire index (tens of thousands of files).
    catalog = rows("""SELECT id,relative_path,acquisition_epoch,dt,samples,lid FROM das_recordings
        WHERE time_verified AND mapping_verified AND lid IS NOT NULL
        AND acquisition_epoch >= %s AND acquisition_epoch < %s ORDER BY acquisition_epoch,id""", (start, end))
    stations = rows("SELECT lid,name,latitude,longitude FROM weather_stations WHERE latitude IS NOT NULL AND longitude IS NOT NULL")
    forecasts = rows("""SELECT w.lid,extract(epoch from w.source_time)::double precision AS valid,
        extract(epoch from w.forecast_updated_at)::double precision AS issued,
        extract(epoch from greatest(w.collected_at,t.collected_at))::double precision AS collected,
        w.value AS wind,t.value AS temperature
        FROM weather_obs w JOIN weather_obs_types wt ON wt.type=w.type AND wt.abv='wspd'
        JOIN weather_obs t ON t.lid=w.lid AND t.source_time=w.source_time AND t.forecast_updated_at=w.forecast_updated_at
        JOIN weather_obs_types tt ON tt.type=t.type AND tt.abv='temp'
        WHERE w.source_time BETWEEN to_timestamp(%s) AND to_timestamp(%s)
        AND w.forecast_updated_at IS NOT NULL AND w.collected_at IS NOT NULL AND t.collected_at IS NOT NULL
        ORDER BY w.source_time,w.forecast_updated_at,w.collected_at""", (start - 7200, end))
    weather = defaultdict(list)
    for row in forecasts:
        if all(math.isfinite(row[k]) for k in ("valid", "issued", "collected", "wind", "temperature")) and row["wind"] >= 0:
            weather[row["lid"]].append(row)
    candidates, seen = [], set()
    for rec in catalog:
        width = max(1, round(10 / rec["dt"]))
        for frame in range(rec["samples"] // width):
            epoch = rec["acquisition_epoch"] + frame * width * rec["dt"]
            key = (rec["lid"], int(epoch // (60 * args.sample_minutes)))
            if key not in seen:
                candidates.append((rec, frame, epoch))
                seen.add(key)
    if not candidates:
        raise ValueError("No verified complete recording frames in the training interval")
    ident = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + hashlib.sha256(json.dumps([start, end, args.wind_max, args.temperature_min]).encode()).hexdigest()[:8]
    manifest = dict(version=VERSION, id=ident, training_start=start, training_end=end,
                    band=[1., 10.], rules=dict(wind_max=args.wind_max, temperature_min=args.temperature_min,
                    max_weather_age_seconds=7200, max_station_distance_m=5000, sample_minutes=args.sample_minutes,
                    minimum_fit_frames=120, minimum_fit_hours=3, minimum_fit_dates=2,
                    relative_scale_floor=.05), configurations={}, exclusions=[],
                    weather=forecasts, stations=stations)
    configs = {}
    # A disk-backed matrix bounds memory even for multi-day, 25k-channel archives.
    with tempfile.TemporaryDirectory(prefix="training-", dir=root) as temporary:
        for number, (item, frame, epoch) in enumerate(candidates):
            try:
                rec = rows("SELECT * FROM das_recordings WHERE id=%s", (item["id"],))[0]
                key = fingerprint(rec)
                if key not in configs:
                    positions = fibre_positions(rec["lid"])
                    located, counts = resolve_positions(rec, positions, interpolation_regions(rec, positions))
                    nearest = {}
                    for p in located:
                        station = min(stations, key=lambda s: geographic_distance(p, s)) if stations else None
                        if station is not None and geographic_distance(p, station) <= 5000:
                            nearest[p["recording_channel"]] = station["lid"]
                    n = len(rec["channels"])
                    configs[key] = dict(recording=rec, mapping_counts=counts,
                        stations=np.array([nearest.get(ch, -1) for ch in rec["channels"]]),
                        matrix=np.memmap(Path(temporary) / key, mode="w+", dtype="float32", shape=(len(candidates), len(METRICS), n)),
                        frames=[], epochs=[], contexts=[], identities=[])
                config = configs[key]
                context = {sid: weather_at(weather[sid], epoch) for sid in set(config["stations"].tolist()) if sid != -1}
                # Keep windy data for a separate comparison, never fit it as normal.
                if not any(context.values()):
                    manifest["exclusions"].append(dict(recording_id=rec["id"], frame=frame, reason="No timely weather"))
                    continue
                metrics = metric_frame(rec, frame)
                index = len(config["frames"])
                for m, name in enumerate(METRICS):
                    config["matrix"][index, m] = metrics["values"][name]
                config["frames"].append([rec["relative_path"], frame])
                config["epochs"].append(epoch)
                config["contexts"].append(context)
                config["identities"].append(dict(recording_id=rec["id"], size_bytes=rec["size_bytes"], mtime_ns=rec["mtime_ns"]))
            except (ValueError, OSError, KeyError) as exc:
                manifest["exclusions"].append(dict(recording_id=item["id"], frame=frame, reason=str(exc)))
            if number % 100 == 0:
                print(f"Measured {number + 1}/{len(candidates)} sampled frames", flush=True)
        for key, config in configs.items():
            rec = config["recording"]
            n = len(rec["channels"])
            arrays = dict(channels=np.array(rec["channels"]), eligible=np.zeros(n, dtype=bool),
                          station=config["stations"], fit_count=np.zeros(n, dtype=int))
            for name in METRICS:
                for stat in ("median", "mad", "scale"):
                    arrays[name + "_" + stat] = np.full(n, np.nan)
            report, fit_frames, validation_frames = {}, set(), set()
            for sid in sorted(set(config["stations"].tolist())):
                if sid == -1:
                    continue
                cols = np.flatnonzero(config["stations"] == sid)
                calm, windy = [], []
                for i, context in enumerate(config["contexts"]):
                    w = context.get(sid)
                    if w and w["wind"] <= args.wind_max and w["temperature"] > args.temperature_min:
                        calm.append(i)
                    elif w and w["wind"] > args.wind_max:
                        windy.append(i)
                fit, validation, qualified = split_calm(calm, config["epochs"])
                report[str(sid)] = dict(channels=len(cols), calm_frames=len(calm), fit_frames=len(fit),
                                       validation_frames=len(validation), qualified=qualified, metrics={})
                if not qualified:
                    continue
                arrays["eligible"][cols] = True
                arrays["fit_count"][cols] = len(fit)
                fit_frames.update(fit); validation_frames.update(validation)
                for m, name in enumerate(METRICS):
                    data = np.asarray(config["matrix"][np.ix_(fit, [m], cols)])[:, 0, :]
                    median, mad, scale = robust_fit(data)
                    for stat, values in (("median", median), ("mad", mad), ("scale", scale)):
                        arrays[name + "_" + stat][cols] = values
                    metric_report = dict(floored_channels=int(np.sum(scale > 1.4826 * mad)), zero_scale_channels=int(np.sum(scale <= 0)))
                    for label, indices in (("held_out_calm", validation), ("windy", windy)):
                        data = np.asarray(config["matrix"][np.ix_(indices, [m], cols)])[:, 0, :]
                        metric_report[label] = distribution(score(data, median, scale, np.ones(len(cols), dtype=bool)))
                    report[str(sid)]["metrics"][name] = metric_report
            filename = f"{ident}-{key}.npz"
            np.savez_compressed(root / filename, **arrays)
            manifest["configurations"][key] = dict(file=filename, lid=rec["lid"], channels=n,
                qualified_channels=int(arrays["eligible"].sum()), mapping_counts=config["mapping_counts"],
                station_reports=report, fit_frames=[config["frames"][i] for i in sorted(fit_frames)],
                validation_frames=[config["frames"][i] for i in sorted(validation_frames)],
                sources=[dict(path=p, frame=f, epoch=t, **identity) for (p,f),t,identity in zip(config["frames"],config["epochs"],config["identities"])])
    finalize_manifest(manifest)
    atomic_json(root / (ident + ".json"), manifest)
    qualified = sum(c["qualified_channels"] for c in manifest["configurations"].values())
    if args.activate:
        if not qualified:
            raise ValueError(f"No channels meet calm coverage requirements. Report: {root / (ident + '.json')}; existing baseline preserved")
        atomic_json(root / "active.json", manifest)
    print(json.dumps(dict(id=ident, qualified_channels=qualified, report=str(root / (ident + '.json')), activated=args.activate)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=float, help="UTC epoch; default last 30 days")
    parser.add_argument("--end", type=float, help="UTC epoch; default training start time")
    parser.add_argument("--wind-max", type=float, default=3)
    parser.add_argument("--temperature-min", type=float, default=2)
    parser.add_argument("--sample-minutes", type=int, default=1)
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args()
    if args.sample_minutes < 1 or not math.isfinite(args.wind_max) or args.wind_max < 0 or not math.isfinite(args.temperature_min):
        parser.error("Invalid training thresholds or sampling interval")
    train(args)


if __name__ == "__main__":
    main()
