"""Offline DAS window classification. Run with python3 -m src.Capture.event_ml."""

import argparse
import csv
import json
from pathlib import Path

import numpy as np

CLASSES = ["Normal Operations", "Ice Loading", "Wind Galloping", "External Interference"]
FEATURES = ["rms", "ac_rms", "peak", "crest_factor", "kurtosis",
            "dominant_hz", "low_power_fraction", "spectral_entropy",
            "spatial_rms_cv", "mean_shift", "temperature", "wind_speed",
            "wind_sin", "wind_cos", "humidity", "temperature_missing",
            "wind_speed_missing", "direction_missing", "humidity_missing"]


def extract_features(data, sample_rate, weather=None):
    """Input is samples x channels; amplitudes retain the input signal's units."""
    x = np.asarray(data, dtype=float)
    if x.ndim != 2 or x.shape[0] < 8 or x.shape[1] < 1:
        raise ValueError("Expected at least 8 samples and one channel")
    if not np.isfinite(x).all() or not np.isfinite(sample_rate) or sample_rate <= 0:
        raise ValueError("Signal and positive sample rate must be finite")
    ac = x - x.mean(axis=0)
    rms = float(np.sqrt(np.mean(x ** 2)))
    ac_rms = float(np.sqrt(np.mean(ac ** 2)))
    peak = float(np.max(np.abs(ac)))
    power = np.mean(abs(np.fft.rfft(ac * np.hanning(len(x))[:, None], axis=0)) ** 2, axis=1)
    power[0] = 0
    frequencies = np.fft.rfftfreq(len(x), 1 / sample_rate)
    total = float(power.sum())
    p = power / total if total else np.zeros_like(power)
    positive = p[p > 0]
    channel_rms = np.sqrt(np.mean(ac ** 2, axis=0))
    values = [rms, ac_rms, peak, peak / ac_rms if ac_rms else 0,
              float(np.mean(ac ** 4)) / ac_rms ** 4 if ac_rms else 0,
              float(frequencies[np.argmax(power)]) if total else 0,
              float(p[(frequencies > 0) & (frequencies <= 3)].sum()),
              float(-np.sum(positive * np.log(positive)) / np.log(len(p))),
              float(channel_rms.std() / channel_rms.mean()) if channel_rms.mean() else 0,
              float(np.mean(x[-len(x)//4:]) - np.mean(x[:len(x)//4]))]
    weather = weather or {}
    raw = [weather.get(k) for k in ("temperature", "wind_speed", "wind_direction", "humidity")]
    missing = [v is None or v == "" for v in raw]
    t, w, d, h = [0.0 if m else float(v) for v, m in zip(raw, missing)]
    if not np.isfinite([t, w, d, h]).all() or w < 0 or not 0 <= h <= 100 or not 0 <= d <= 360:
        raise ValueError("Invalid weather values (humidity 0–100, direction 0–360, wind >= 0)")
    values += [t, w, float(np.sin(np.deg2rad(d))) if not missing[2] else 0,
               float(np.cos(np.deg2rad(d))) if not missing[2] else 0, h]
    values += list(map(float, missing))
    if not np.isfinite(values).all():
        raise ValueError("Feature overflow; check signal scaling")
    return dict(zip(FEATURES, values))


def read_window(path, start, stop, channel_start, channel_stop):
    """Read an explicit half-open window without loading the entire recording."""
    import h5py
    with h5py.File(path, "r") as recording:
        data = recording["data"]
        if data.ndim != 2 or not (0 <= start < stop <= data.shape[0]):
            raise ValueError("Invalid sample bounds or dataset shape")
        if not 0 <= channel_start < channel_stop <= data.shape[1]:
            raise ValueError("Invalid channel bounds")
        return data[start:stop, channel_start:channel_stop]


def load_manifest(path):
    path = Path(path)
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError("Manifest is empty")
    vectors, labels, groups = [], [], []
    file_groups = {}
    for row in rows:
        if row["label"] not in CLASSES or not row["group"].strip():
            raise ValueError("Every row needs a supported label and recording/session group")
        recording = (path.parent / row["path"]).resolve()
        if file_groups.setdefault(recording, row["group"]) != row["group"]:
            raise ValueError("All windows from one recording must use the same group")
        bounds = [int(row[k]) for k in ("start_sample", "stop_sample", "channel_start", "channel_stop")]
        features = extract_features(read_window(recording, *bounds), float(row["sample_rate_hz"]), row)
        vectors.append([features[k] for k in FEATURES])
        labels.append(row["label"])
        groups.append(row["group"])
    return np.asarray(vectors), np.asarray(labels), np.asarray(groups)


def train(manifest, output):
    import joblib
    import sklearn
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import classification_report, confusion_matrix
    from sklearn.model_selection import StratifiedGroupKFold

    x, y, groups = load_manifest(manifest)
    if set(y) != set(CLASSES):
        raise ValueError("Training requires labeled examples of all four classes")
    if any(len(set(groups[y == label])) < 3 for label in CLASSES):
        raise ValueError("Each class requires at least three independent recording/session groups")
    def make_model():
        return RandomForestClassifier(n_estimators=300, min_samples_leaf=2,
                                      class_weight="balanced", random_state=42, n_jobs=-1)
    predictions = np.empty(len(y), dtype=object)
    folds = []
    for train_indices, test_indices in StratifiedGroupKFold(3, shuffle=True, random_state=42).split(x, y, groups):
        if set(y[train_indices]) != set(CLASSES) or set(y[test_indices]) != set(CLASSES):
            raise ValueError("Grouped folds lack classes; collect more independent labeled sessions")
        model = make_model().fit(x[train_indices], y[train_indices])
        predictions[test_indices] = model.predict(x[test_indices])
        folds.append({"train_groups": sorted(set(groups[train_indices])),
                      "test_groups": sorted(set(groups[test_indices]))})
    report = {"classes": CLASSES, "classification_report": classification_report(
        y, predictions, labels=CLASSES, output_dict=True, zero_division=0),
        "confusion_matrix": confusion_matrix(y, predictions, labels=CLASSES).tolist(),
        "folds": folds, "samples": len(y)}
    model = make_model().fit(x, y)
    joblib.dump({"version": 1, "features": FEATURES, "classes": CLASSES,
                 "sklearn_version": sklearn.__version__, "model": model}, output)
    Path(str(output) + ".metrics.json").write_text(json.dumps(report, indent=2))
    return report


def classify_window(artifact, data, sample_rate, weather=None, threshold=0.7):
    """Scores are uncalibrated model probabilities, not physical severity."""
    if not 0 <= threshold <= 1:
        raise ValueError("Threshold must be between zero and one")
    if artifact.get("version") != 1 or artifact.get("features") != FEATURES or artifact.get("classes") != CLASSES:
        raise ValueError("Incompatible model artifact")
    features = extract_features(data, sample_rate, weather)
    model = artifact["model"]
    probabilities = dict(zip(model.classes_, map(float, model.predict_proba(
        [[features[k] for k in FEATURES]])[0])))
    label = max(probabilities, key=probabilities.get)
    return {"predicted_class": label, "needs_review": probabilities[label] < threshold,
            "probabilities": {k: probabilities[k] for k in CLASSES},
            "window_duration_s": len(data) / sample_rate,
            "measurements": {k: features[k] for k in ("rms", "ac_rms", "peak", "dominant_hz")}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    training = commands.add_parser("train")
    training.add_argument("manifest")
    training.add_argument("model")
    inference = commands.add_parser("predict")
    inference.add_argument("model")
    inference.add_argument("recording")
    inference.add_argument("--sample-rate", type=float, required=True)
    inference.add_argument("--window-samples", type=int, required=True)
    inference.add_argument("--channel-start", type=int, required=True)
    inference.add_argument("--channel-stop", type=int, required=True)
    inference.add_argument("--threshold", type=float, default=0.7)
    inference.add_argument("--weather", help="JSON object with time-aligned weather")
    args = parser.parse_args()
    if args.command == "train":
        print(json.dumps(train(args.manifest, args.model), indent=2))
        return
    import h5py
    import joblib
    if args.window_samples < 8:
        parser.error("--window-samples must be at least 8")
    artifact = joblib.load(args.model)
    weather = json.loads(args.weather) if args.weather else None
    with h5py.File(args.recording, "r") as recording:
        count = recording["data"].shape[0]
    for start in range(0, count, args.window_samples):
        stop = min(start + args.window_samples, count)
        if stop - start < 8:
            continue
        data = read_window(args.recording, start, stop, args.channel_start, args.channel_stop)
        result = classify_window(artifact, data, args.sample_rate, weather, args.threshold)
        result.update(start_s=start / args.sample_rate, stop_s=stop / args.sample_rate,
                      channel_start=args.channel_start, channel_stop=args.channel_stop)
        print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
