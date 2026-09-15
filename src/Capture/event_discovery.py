"""Bounded, offline discovery of DAS signal patterns (not event classification)."""

import argparse
import bisect
import csv
import hashlib
import json
import math
import os
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import h5py
import numpy as np

VERSION = 1
BANDS = ((.1, .5), (.5, 1), (1, 3), (3, 10), (10, 50), (50, 150))
PREPROCESSING = "dataScale; linear detrend per channel; no reversal, unwrap or integration"
CLASSES = ("Normal Operations", "Ice Loading", "Wind Galloping", "External Interference")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def write_csv(path, rows, fields=None):
    path = Path(path)
    fields = fields or (list(rows[0]) if rows else [])
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def stamp(path):
    stat = Path(path).stat()
    return [stat.st_size, stat.st_mtime_ns]


def index_archive(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    if not root.is_dir():
        raise ValueError("Archive must be an existing directory")
    if output == root or root in output.parents:
        raise ValueError("Use an output directory outside the source archive")
    output.mkdir(parents=True, exist_ok=True)
    result = dict(version=VERSION, root=str(root), configurations={}, files=[], skipped=[])
    for path in sorted(p for p in root.rglob("*") if p.suffix.lower() in (".h5", ".hdf5")):
        try:
            before = stamp(path)
            with h5py.File(path, "r") as f:
                data = f["data"]
                if data.ndim != 2 or min(data.shape) < 1:
                    raise ValueError("Expected nonempty samples x channels")
                if data.dtype.kind not in "iuf":
                    raise ValueError("Expected real numeric signal data")
                dt, start = float(f["header/dt"][()]), float(f["header/time"][()])
                scale = float(f["header/dataScale"][()])
                channels = f["header/channels"][()]
                if channels.ndim != 1 or len(channels) != data.shape[1]:
                    raise ValueError("Channel IDs do not match data columns")
                if channels.dtype.kind not in "iu" or len(np.unique(channels)) != len(channels):
                    raise ValueError("Channel IDs must be unique integers")
                if not all(math.isfinite(v) for v in (dt, start, scale)) or dt <= 0 or scale == 0:
                    raise ValueError("Invalid timing or scale")
                datetime.fromtimestamp(start, timezone.utc)
                if "header/missingSamples" not in f:
                    raise ValueError("Missing sample-quality metadata")
                if f["header/missingSamples"].size:
                    raise ValueError("File declares missing samples")
                def scalar(name):
                    value = f[name][()]
                    return value.decode() if isinstance(value, bytes) else np.asarray(value).tolist()
                config = dict(dt=dt, scale=scale, channels=channels.tolist(),
                              unit=scalar("header/unit"), name=scalar("header/name"),
                              gauge_length=scalar("header/gaugeLength"), dtype=str(data.dtype),
                              spatial_unwrap_range=scalar("header/spatialUnwrRange"),
                              sensitivities=scalar("header/sensitivities"))
                if config["unit"] != "rad/(m*s)" or config["name"] != "phase rate per distance":
                    raise ValueError("Unsupported signal representation")
                if "demodSpec/roiDec" in f:
                    config["roi_dec"] = f["demodSpec/roiDec"][()].tolist()
                for name in ("header/instrumentSerial", "header/wavelength", "header/dataType", "fileVersion"):
                    if name in f:
                        config[name] = scalar(name)
                json.dumps(config, allow_nan=False)
                key = digest(config)
                item = dict(path=str(path), stamp=before, start=start, samples=data.shape[0],
                            config=key, synchronized=scalar("header/timeSynchronized")
                            if "header/timeSynchronized" in f else None)
            if stamp(path) != before:
                raise ValueError("File changed during indexing")
            result["configurations"][key] = config
            result["files"].append(item)
        except (OSError, KeyError, ValueError, TypeError, OverflowError) as error:
            result["skipped"].append(dict(path=str(path), reason=str(error)))
    result["files"].sort(key=lambda r: (r["start"], r["path"]))
    write_json(output / "index.json", result)
    return result


def channel_blocks(config, count=16, width=32):
    """Select spread-out blocks without crossing a change in channel spacing."""
    channels = np.asarray(config["channels"])
    delta = np.diff(channels)
    steps = np.asarray(config.get("roi_dec", []), dtype=int)
    if len(steps) and len(np.unique(steps)) != 1:
        raise ValueError("Mixed spatial decimation requires an explicit mapping adapter")
    step = int(steps[0]) if len(steps) else (int(np.min(abs(delta))) if len(delta) else 1)
    if step <= 0:
        raise ValueError("Invalid channel spacing")
    cuts = [0, *(np.flatnonzero(abs(delta) != step) + 1).tolist(), len(channels)]
    candidates = [(i, i + width) for lo, hi in zip(cuts, cuts[1:])
                  for i in range(lo, hi - width + 1, width)]
    if not candidates:
        raise ValueError("No contiguous channel region is wide enough")
    positions = np.linspace(0, len(candidates) - 1, min(count, len(candidates))).round().astype(int)
    return [candidates[i] for i in positions]


def make_windows(index, seconds):
    runs, current, skipped, boundaries = [], [], [], []
    for item in index["files"]:
        if current:
            previous = current[-1]
            dt = index["configurations"][previous["config"]]["dt"]
            gap = item["start"] - previous["start"] - previous["samples"] * dt
            compatible = item["config"] == previous["config"] and abs(gap) <= dt + 1e-6
            boundaries.append(dict(before=previous["path"], after=item["path"],
                                   discrepancy_seconds=gap, joined=compatible))
            if not compatible:
                runs.append(current)
                current = []
        current.append(item)
    if current:
        runs.append(current)
    windows = []
    for run in runs:
        config = index["configurations"][run[0]["config"]]
        dt = config["dt"]
        length = int(math.floor(seconds / dt))
        if length < 8:
            raise ValueError("Window must contain at least eight samples")
        group = "session-" + digest([(f["path"], f["stamp"]) for f in run])[:16]
        offsets = np.cumsum([0] + [f["samples"] for f in run]).tolist()
        total = offsets[-1]
        for start in range(0, total - length + 1, length):
            refs = []
            for i in range(bisect.bisect_right(offsets, start) - 1, len(run)):
                if offsets[i] >= start + length:
                    break
                lo, hi = max(0, start - offsets[i]), min(run[i]["samples"], start + length - offsets[i])
                refs.append(dict(path=run[i]["path"], stamp=run[i]["stamp"], start_sample=lo, stop_sample=hi))
            first = next(f for f in run if f["path"] == refs[0]["path"])
            windows.append(dict(start=first["start"] + refs[0]["start_sample"] * dt,
                                duration=length * dt, refs=refs, config=run[0]["config"], group=group))
        if total % length:
            skipped.append(dict(group=group, reason="Incomplete final window", samples=total % length))
    return windows, skipped, boundaries


def epoch(value, zone=None):
    date = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if date.tzinfo is not None:
        return date.timestamp()
    if not zone:
        raise ValueError("Naive weather timestamps require --weather-timezone")
    tz = ZoneInfo(zone)
    options = [date.replace(tzinfo=tz, fold=fold) for fold in (0, 1)]
    if options[0].utcoffset() != options[1].utcoffset():
        raise ValueError("Ambiguous/nonexistent local weather time; provide an explicit UTC offset")
    return options[0].timestamp()


def load_weather(args, windows):
    if not args.weather_csv and not args.weather_dsn_env:
        return [], "No weather source supplied"
    if not args.confirm_unix_time:
        raise ValueError("Weather joining requires --confirm-unix-time after verifying acquisition timestamps")
    if args.weather_csv:
        with open(args.weather_csv, newline="") as stream:
            source = list(csv.DictReader(stream))
    else:
        if not args.weather_timezone:
            raise ValueError("Database weather requires --weather-timezone")
        import psycopg2
        dsn = os.environ.get(args.weather_dsn_env)
        if not dsn:
            raise ValueError("Weather DSN environment variable is not set")
        tz = ZoneInfo(args.weather_timezone)
        lo = datetime.fromtimestamp(min(w["start"] for w in windows) - args.weather_max_age - 86400, tz).replace(tzinfo=None)
        hi = datetime.fromtimestamp(max(w["start"] for w in windows) + 86400, tz).replace(tzinfo=None)
        connection = psycopg2.connect(dsn)
        try:
            connection.set_session(readonly=True, autocommit=False)
            with connection.cursor() as cursor:
                cursor.execute("SELECT o.lid,o.time,t.abv,o.value FROM weather_obs o "
                               "JOIN weather_obs_types t ON t.type=o.type "
                               "WHERE o.time >= %s AND o.time <= %s ORDER BY o.time,o.id", (lo, hi))
                source = [dict(lid=lid, time=str(time), variable=abv, value=value)
                          for lid, time, abv, value in cursor]
        finally:
            connection.rollback()
            connection.close()
    names = {"temp": "temperature", "wspd": "wind_speed", "wdir": "wind_direction",
             "temperature": "temperature", "wind_speed": "wind_speed", "wind_direction": "wind_direction",
             "humidity": "humidity"}
    rows = []
    for row in source:
        variable = names.get(row["variable"].strip())
        if variable is None:
            continue
        value = float(row["value"])
        if not math.isfinite(value) or (variable == "wind_speed" and value < 0) or (
                variable in ("humidity", "wind_direction") and not 0 <= value <= (100 if variable == "humidity" else 360)):
            raise ValueError("Invalid weather value")
        rows.append(dict(lid=int(row["lid"]), time=epoch(row["time"], args.weather_timezone),
                         source_time=str(row["time"]), variable=variable, value=value))
    return sorted(rows, key=lambda r: r["time"]), "Joined preceding collected forecast values"


class Weather:
    def __init__(self, rows, max_age):
        self.max_age, self.series = max_age, {}
        for row in rows:
            self.series.setdefault((row["lid"], row["variable"]), []).append(row)
        self.times = {key: [r["time"] for r in rows] for key, rows in self.series.items()}

    def at(self, start):
        result = {}
        for lid in sorted({key[0] for key in self.series}):
            station = {}
            for variable in ("temperature", "wind_speed", "wind_direction", "humidity"):
                key = (lid, variable)
                position = bisect.bisect_right(self.times.get(key, []), start) - 1
                row = self.series[key][position] if position >= 0 else None
                age = start - row["time"] if row else None
                stale = row is not None and age > self.max_age
                station[variable] = dict(value=row["value"] if row and not stale else None,
                                         source_time=row["source_time"] if row else None,
                                         age_seconds=age, missing=row is None, stale=stale)
            result[str(lid)] = station
        return result


def select_windows(windows, weather, limit, seed, station=None):
    rng = np.random.default_rng(seed)
    buckets = {}
    for window in windows:
        context = weather.at(window["start"])
        window["weather"] = context
        values = context.get(str(station), {})
        temp, wind = [values.get(k, {}).get("value") for k in ("temperature", "wind_speed")]
        bucket = "unknown" if temp is None or wind is None else (
            ("cold" if temp < 0 else "nonfreezing") + "-" + ("low" if wind < 3 else "medium" if wind <= 8 else "high"))
        window["weather_stratum"] = bucket
        buckets.setdefault(bucket if station is not None else "all", []).append(window)
    for rows in buckets.values():
        rng.shuffle(rows)
    chosen = []
    while len(chosen) < limit and any(buckets.values()):
        for key in sorted(buckets):
            if buckets[key] and len(chosen) < limit:
                chosen.append(buckets[key].pop())
    return sorted(chosen, key=lambda r: r["start"])


def read_signal(window, config, lo, hi):
    count = sum(r["stop_sample"] - r["start_sample"] for r in window["refs"])
    data = np.empty((count, hi - lo), dtype=np.float64)
    offset = 0
    for ref in window["refs"]:
        if stamp(ref["path"]) != ref["stamp"]:
            raise ValueError("Source file changed; rebuild index")
        n = ref["stop_sample"] - ref["start_sample"]
        with h5py.File(ref["path"], "r") as recording:
            data[offset:offset+n] = recording["data"][ref["start_sample"]:ref["stop_sample"], lo:hi]
        if stamp(ref["path"]) != ref["stamp"]:
            raise ValueError("Source file changed during read")
        offset += n
    data *= config["scale"]
    return data


def features(data, dt):
    from scipy.signal import detrend
    if data.ndim != 2 or len(data) < 8 or not np.isfinite(data).all():
        raise ValueError("Invalid signal window")
    x = detrend(data, axis=0, type="linear")
    rms = float(np.sqrt(np.mean(x*x)))
    channel_rms = np.sqrt(np.mean(x*x, axis=0))
    power = np.mean(abs(np.fft.rfft(x * np.hanning(len(x))[:, None], axis=0)) ** 2, axis=1)
    power[0] = 0
    freq = np.fft.rfftfreq(len(x), dt)
    total = float(power.sum())
    p = power / total if total else np.zeros_like(power)
    positive = p[p > 0]
    result = dict(rms=rms, crest_factor=float(np.max(abs(x))) / rms if rms else 0.,
                  kurtosis=float(np.mean(x**4)) / rms**4 if rms else 0.,
                  dominant_hz=float(freq[np.argmax(power)]) if total else 0.,
                  spectral_entropy=float(-np.sum(positive*np.log(positive))/np.log(len(p))),
                  spatial_rms_cv=float(channel_rms.std()/channel_rms.mean()) if rms else 0.)
    for low, high in BANDS:
        result[f"power_{low:g}_{high:g}_hz"] = float(p[(freq >= low) & (freq < high)].sum())
    if not np.isfinite(list(result.values())).all():
        raise ValueError("Nonfinite features")
    return result


def learn(rows, feature_names, seed):
    import sklearn
    from sklearn.preprocessing import RobustScaler
    from sklearn.cluster import KMeans
    from sklearn.ensemble import IsolationForest
    if len(rows) < 10:
        return None, "Fewer than ten valid rows; fitting skipped"
    x = np.asarray([[r[k] for k in feature_names] for r in rows])
    scaler = RobustScaler()
    scaled = scaler.fit_transform(x)
    count = min(6, len(np.unique(scaled, axis=0)))
    clusters = KMeans(n_clusters=count, random_state=seed, n_init=10).fit(scaled)
    anomaly = IsolationForest(n_estimators=200, random_state=seed, n_jobs=1).fit(scaled)
    scores = -anomaly.score_samples(scaled)
    distances = np.linalg.norm(scaled - clusters.cluster_centers_[clusters.labels_], axis=1)
    for row, cluster, score, distance in zip(rows, clusters.labels_, scores, distances):
        row.update(cluster=int(cluster), anomaly_score=float(score), cluster_distance=float(distance))
    return dict(version=VERSION, sklearn_version=sklearn.__version__, features=feature_names,
                preprocessing=PREPROCESSING, scaler=scaler, clusters=clusters, anomaly=anomaly), "Exploratory fit; no accuracy estimate"


def analyze(args):
    import joblib
    index_path = Path(args.index).resolve()
    index = json.loads(index_path.read_text())
    if index["version"] != VERSION:
        raise ValueError("Unsupported index version")
    output = Path(args.output).resolve()
    root = Path(index["root"])
    if output == root or root in output.parents:
        raise ValueError("Use an output directory outside the source archive")
    output.mkdir(parents=True, exist_ok=True)
    windows, skipped, boundaries = make_windows(index, args.window_seconds)
    if not windows:
        raise ValueError("No complete windows available")
    weather_rows, weather_status = load_weather(args, windows)
    weather = Weather(weather_rows, args.weather_max_age)
    if args.station is not None and not weather_rows:
        raise ValueError("Weather-stratified sampling requires weather records")
    if args.station is not None and args.station not in {row["lid"] for row in weather_rows}:
        raise ValueError("Selected station is absent from the supplied weather records")
    selected = select_windows(windows, weather, args.max_windows, args.seed, args.station)
    write_json(output / "weather.json", weather_rows)
    config = {k: v for k, v in vars(args).items() if k not in ("func", "output", "index")}
    cache_path = output / "feature-cache.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    rows, reused, feature_names = [], 0, []
    for number, window in enumerate(selected):
        metadata = index["configurations"][window["config"]]
        try:
            if .5 / metadata["dt"] < 150:
                raise ValueError("Sample rate does not support the full feature bands through 150 Hz")
            blocks = channel_blocks(metadata, args.blocks, args.channels_per_block)
        except ValueError as error:
            skipped.append(dict(start=window["start"], reason=str(error)))
            continue
        for lo, hi in blocks:
            key = digest([VERSION, PREPROCESSING, window["refs"], window["config"], lo, hi])
            try:
                for ref in window["refs"]:
                    if stamp(ref["path"]) != ref["stamp"]:
                        raise ValueError("Source changed; rebuild index")
                if key in cache:
                    values = cache[key]
                    reused += 1
                else:
                    values = features(read_signal(window, metadata, lo, hi), metadata["dt"])
                    cache[key] = values
                feature_names = list(values)
                rows.append(dict(window_id=key, start_epoch=window["start"], duration_seconds=window["duration"],
                                 group=window["group"], config=window["config"],
                                 channel_start=lo, channel_stop=hi,
                                 channel_ids=json.dumps(metadata["channels"][lo:hi]),
                                 sample_rate_hz=1/metadata["dt"], refs=json.dumps(window["refs"]),
                                 weather=json.dumps(window["weather"]), weather_stratum=window["weather_stratum"],
                                 **values))
            except (ValueError, OSError) as error:
                skipped.append(dict(start=window["start"], channel_start=lo, reason=str(error)))
        write_json(cache_path, cache)
        print(f"Processed window {number+1}/{len(selected)}; feature rows {len(rows)}", flush=True)
    # Never mix acquisition configurations in a fitted model.
    artifacts, statuses = {}, {}
    for key in sorted({r["config"] for r in rows}):
        subset = [r for r in rows if r["config"] == key]
        artifact, status = learn(subset, feature_names, args.seed)
        statuses[key] = status
        if artifact:
            artifact["acquisition"] = index["configurations"][key]
            artifacts[key] = artifact
    for row in rows:
        for field in ("cluster", "anomaly_score", "cluster_distance"):
            row.setdefault(field, "")
    joblib.dump(dict(version=VERSION, models=artifacts), output / "discovery-model.joblib")
    write_csv(output / "features.csv", rows, list(rows[0]) if rows else ["window_id"])
    ranked = sorted(rows, key=lambda r: (-float(r["anomaly_score"]) if r["anomaly_score"] != "" else 0, r["window_id"]))
    representatives = {}
    for row in rows:
        if row["cluster"] != "":
            key = (row["config"], row["cluster"])
            if key not in representatives or row["cluster_distance"] < representatives[key]["cluster_distance"]:
                representatives[key] = row
    representative_ids = {r["window_id"] for r in representatives.values()}
    prior_review = {}
    if (output / "review.csv").exists():
        with (output / "review.csv").open(newline="") as stream:
            prior_review = {row["window_id"]: row for row in csv.DictReader(stream)}
    review = [dict(rank=i+1, representative=r["window_id"] in representative_ids,
                   label=prior_review.get(r["window_id"], {}).get("label", ""),
                   label_verified=prior_review.get(r["window_id"], {}).get("label_verified", ""), **r)
              for i, r in enumerate(ranked)]
    # Keep reviewed rows that no longer appear in this sampling run separately.
    current_ids = {r["window_id"] for r in review}
    retired = [r for key, r in prior_review.items() if key not in current_ids and r.get("label")]
    if retired:
        archive_path = output / "retired-review.csv"
        if archive_path.exists():
            with archive_path.open(newline="") as stream:
                retired = list(csv.DictReader(stream)) + retired
        write_csv(archive_path, retired)
    write_csv(output / "review.csv", review, list(review[0]) if review else ["rank", "label", "label_verified"])
    populations = {}
    for row in rows:
        key = f'{row["config"][:12]}:{row["cluster"]}'
        populations[key] = populations.get(key, 0) + 1
    summary = dict(version=VERSION, index=str(index_path), index_digest=digest(index), configuration=config,
                   preprocessing=PREPROCESSING, timestamp_interpretation="Unix seconds (confirmed)" if args.confirm_unix_time else "Unix seconds (unconfirmed; no weather join)",
                   weather_status=weather_status, available_windows=len(windows), selected_windows=len(selected),
                   feature_rows=len(rows), reused_feature_rows=reused, cluster_populations=populations,
                   model_status=statuses, skipped=index["skipped"]+skipped, boundaries=boundaries,
                   limitations=["Scores are review priorities, not class probabilities", "Channel blocks have no assigned physical location",
                                "Scaled phase-rate spectra; wrapping and sensor calibration need independent validation"])
    write_json(output / "summary.json", summary)
    return summary


def export_review(review_path, output):
    with Path(review_path).open(newline="") as stream:
        reviewed = list(csv.DictReader(stream))
    rows, seen, file_groups = [], set(), {}
    for row in reviewed:
        if not row["label"].strip():
            continue
        if row["label"] not in CLASSES or row.get("label_verified", "").lower() not in ("true", "yes", "1"):
            raise ValueError("Every labeled row requires a supported class and label_verified=true")
        if not row["group"].strip():
            raise ValueError("A recording/session group is required")
        for ref in json.loads(row["refs"]):
            if stamp(ref["path"]) != ref["stamp"]:
                raise ValueError("Reviewed source file changed")
            if file_groups.setdefault(ref["path"], row["group"]) != row["group"]:
                raise ValueError("All windows from a file must share a group")
            if ref["stop_sample"] - ref["start_sample"] < 8:
                raise ValueError("A constituent slice is shorter than the supervised reader minimum of 8 samples")
            key = (ref["path"], ref["start_sample"], ref["stop_sample"], row["channel_start"], row["channel_stop"])
            if key in seen:
                raise ValueError("Duplicate reviewed sample slice")
            seen.add(key)
            rows.append(dict(path=ref["path"], start_sample=ref["start_sample"], stop_sample=ref["stop_sample"],
                             channel_start=row["channel_start"], channel_stop=row["channel_stop"],
                             sample_rate_hz=row["sample_rate_hz"], label=row["label"], group=row["group"],
                             temperature="", wind_speed="", wind_direction="", humidity=""))
    if not rows:
        raise ValueError("No verified labels to export")
    write_csv(output, rows)
    return len(rows)


def positive(value):
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise argparse.ArgumentTypeError("Must be finite and positive")
    return result


def positive_int(value):
    result = int(value)
    if result <= 0:
        raise argparse.ArgumentTypeError("Must be positive")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    index = commands.add_parser("index")
    index.add_argument("archive")
    index.add_argument("output")
    analysis = commands.add_parser("analyze")
    analysis.add_argument("index")
    analysis.add_argument("output")
    analysis.add_argument("--window-seconds", type=positive, default=60.)
    analysis.add_argument("--blocks", type=positive_int, default=16)
    analysis.add_argument("--channels-per-block", type=positive_int, default=32)
    analysis.add_argument("--max-windows", type=positive_int, default=120)
    analysis.add_argument("--seed", type=int, default=42)
    weather = analysis.add_mutually_exclusive_group()
    weather.add_argument("--weather-csv")
    weather.add_argument("--weather-dsn-env", help="Environment variable containing a PostgreSQL DSN (requires psycopg2)")
    analysis.add_argument("--weather-timezone")
    analysis.add_argument("--confirm-unix-time", action="store_true")
    analysis.add_argument("--weather-max-age", type=positive, default=7200.)
    analysis.add_argument("--station", type=int, help="Explicit weather station for stratified sampling; no geographic assignment")
    export = commands.add_parser("export-review")
    export.add_argument("review")
    export.add_argument("output")
    args = parser.parse_args()
    try:
        if args.command == "index":
            result = index_archive(args.archive, args.output)
            print(f'Indexed {len(result["files"])} files; skipped {len(result["skipped"])}')
        elif args.command == "analyze":
            result = analyze(args)
            print(f'Wrote {result["feature_rows"]} feature rows; reused {result["reused_feature_rows"]}')
        else:
            print(f"Exported {export_review(args.review, args.output)} verified slices (supervised reader uses raw stored values)")
    except (ValueError, OSError, KeyError, ImportError) as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    main()
