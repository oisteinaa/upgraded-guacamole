import json
from datetime import datetime, timezone

import h5py
import numpy as np
import pytest

from src.Mapui import calm, metrics, stitched_signals
from src.Mapui.signals import inspect_recording
from src.Mapui.train_calm import weather_at, split_calm


def test_robust_backgrounds_outliers_and_floor():
    x = np.tile([10., 100., 0.], (200, 1))
    x[-5:, :2] *= 100
    median, mad, scale = calm.robust_fit(x)
    np.testing.assert_equal(median, [10, 100, 0])
    z = calm.score([15, 150, 0], median, scale, [True, True, True])
    assert z[:2].tolist() == [10, 10]
    assert np.isnan(z[2])
    assert calm.json_values(z) == [10, 10, None]


def test_weather_excludes_future_issue_collection_and_stale():
    items = [dict(valid=100, issued=90, collected=105, wind=1, temperature=5),
             dict(valid=100, issued=110, collected=115, wind=0, temperature=6),
             dict(valid=200, issued=150, collected=205, wind=0, temperature=6)]
    assert weather_at(items, 104) is None
    assert weather_at(items, 109) is items[0]
    assert weather_at(items, 120) is items[1]
    assert weather_at(items, 7406) is None


def test_chronological_holdout_and_minimum_coverage():
    base = datetime(2026, 9, 28, tzinfo=timezone.utc).timestamp()
    epochs = [base + hour * 3600 + minute * 60 for hour in [0, 1, 24, 25, 26, 27] for minute in range(60)]
    fit, hold, qualified = split_calm(list(range(len(epochs))), epochs)
    assert qualified and len(fit) == 240 and len(hold) == 120
    assert max(epochs[i] for i in fit) < min(epochs[i] for i in hold)
    assert not split_calm(list(range(120)), epochs)[2]


@pytest.fixture
def reference(tmp_path, monkeypatch):
    monkeypatch.setenv("DAS_ARCHIVE_ROOT", str(tmp_path))
    monkeypatch.setenv("DAS_METRIC_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("DAS_CALM_BASELINES", str(tmp_path / "baseline"))
    root = calm.artifact_root(); root.mkdir()
    records = []
    # 12-second files deliberately put stitched origin off the source-frame grid.
    for file in range(2):
        path = tmp_path / f"{file}.hdf5"
        time = np.arange(1200) * .01
        with h5py.File(path, "w") as f:
            f["data"] = np.column_stack([np.sin(2 * np.pi * 3 * time), 10 * np.sin(2 * np.pi * 4 * time), np.ones(len(time))])
            for name, value in dict(time=1000 + file * 12, dt=.01, channels=[4, 8, 100], unit="rad", dataScale=1,
                                    missingSamples=np.array([], dtype=int)).items():
                f["header/" + name] = value
        rec = inspect_recording(path)
        rec.update(id=file + 1, lid=1, time_verified=True, mapping_verified=True, processing="stored values × dataScale")
        records.append(rec)
    key = calm.fingerprint(records[0])
    arrays = dict(channels=np.array([4, 8, 100]), eligible=np.array([True, True, False]))
    for name in metrics.METRICS:
        arrays[name + "_median"] = np.array([1., 10., 0.])
        arrays[name + "_mad"] = np.array([.1, 1., 0.])
        arrays[name + "_scale"] = np.array([.14826, 1.4826, 0.])
    np.savez_compressed(root / "fixture.npz", **arrays)
    manifest = dict(version=calm.VERSION, id="fixture", training_start=0, training_end=900, band=[1., 10.],
                    configurations={key: dict(file="fixture.npz", fit_frames=[[records[0]["relative_path"], 0]])})
    (root / "active.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(stitched_signals, "rows", lambda *args: records)
    return records


def test_config_mismatch_missing_mapping_and_unsupported_band(reference):
    rec = reference[0]
    assert calm.reference(dict(rec, mapping_verified=False))[1] is None
    assert calm.reference(dict(rec, mapping_verified=False), illustrative=True)[1] is not None
    assert calm.reference(dict(rec, unit="other"))[1] is None
    frame = metrics.metric_frame(rec, 0, 2, 8)
    status, values = calm.normalize_frame(rec, frame, "band_rms")
    assert status["status"] == "unavailable" and np.isnan(values).all()


def test_partial_frames_and_unqualified_channels_are_gaps(reference):
    rec = reference[0]
    status, values = calm.normalize_frame(rec, metrics.metric_frame(rec, 0))
    assert status["training_reference"] and status["available_channels"] == 2
    assert np.isnan(values[-1])
    status, values = calm.normalize_frame(rec, metrics.metric_frame(rec, 1))
    assert status["status"] == "unavailable" and np.isnan(values).all()


def test_map_live_and_stitched_zoom_use_identical_source_frames(reference, monkeypatch):
    rec = reference[1]
    full = calm.activity(reference, [4, 8, 100], 12, 22, 1000)
    zoom = calm.activity(reference, [4, 8, 100], 14, 15, 1000)
    assert full["scores"] == zoom["scores"]
    frame = metrics.metric_frame(rec, 0)
    _, expected = calm.normalize_frame(rec, frame)
    assert full["scores"]["ac_rms"][0] == calm.json_values(expected)
    signal = stitched_signals.read_stitched_signal(rec, 4, 2, 1)
    assert signal["normalization"]["starts"] == [0]
    assert signal["normalization"]["scores"] == full["scores"]
    live = calm.live_activity(rec)
    assert live["profile"]["values"][:2] == calm.json_values(expected[:2])
    assert live["heatmap"]["values"][1] == [None] * len(live["heatmap"]["values"][1])
    output = dict(data=dict(features=[dict(properties=dict(recording_channel=ch, value=frame["values"]["ac_rms"][i])) for i, ch in enumerate(rec["channels"])]))
    calm.add_map_normalization(output, rec, frame, "ac_rms")
    assert [f["properties"]["calm_score"] for f in output["data"]["features"]] == calm.json_values(expected)


def test_retraining_invalidates_reference_and_demo_identity(reference):
    before = calm.identity()
    path = calm.artifact_root() / "active.json"
    data = json.loads(path.read_text()); data["id"] = "replacement"
    path.write_text(json.dumps(data))
    assert calm.identity() != before


def test_timestamp_rounding_does_not_show_previous_frame(reference):
    reference[0]["acquisition_epoch"] += .001
    value = calm.activity(reference, start=0, end=10, epoch=reference[1]["acquisition_epoch"])
    assert value["starts"] == [0]


def test_missing_baseline_keeps_explicit_status(tmp_path, monkeypatch):
    monkeypatch.setenv("DAS_CALM_BASELINES", str(tmp_path))
    assert calm.reference({})[0]["status"] == "unavailable"
