import json
import os
from datetime import datetime, timezone

import h5py
import numpy as np
import pytest

from src.Mapui import calm, metrics, stitched_signals
from src.Mapui.signals import inspect_recording
from src.Mapui.train_calm import weather_at, split_calm, finalize_manifest, compatible_subset


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
    stat = path.stat()
    data = json.loads(path.read_text()); data["id"] = "replacement"
    path.write_text(json.dumps(data))
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    assert calm.identity() != before


def test_timestamp_rounding_does_not_show_previous_frame(reference):
    reference[0]["acquisition_epoch"] += .001
    value = calm.activity(reference, start=0, end=10, epoch=reference[1]["acquisition_epoch"])
    assert value["starts"] == [0]


def test_missing_baseline_keeps_explicit_status(tmp_path, monkeypatch):
    monkeypatch.setenv("DAS_CALM_BASELINES", str(tmp_path))
    assert calm.reference({})[0]["status"] == "unavailable"


@pytest.mark.parametrize("field,value", [("gaugeLength", 16.34), ("channels", [8, 16, 104])])
def test_new_gauge_or_sampling_cannot_reuse_old_baseline(reference, field, value):
    rec = reference[0]
    path = stitched_signals.safe_path(rec["relative_path"])
    with h5py.File(path, "a") as f:
        if "header/" + field in f:
            del f["header/" + field]
        f["header/" + field] = value
    rec.update(inspect_recording(path))
    info, arrays = calm.reference(rec)
    assert arrays is None
    assert info["note"] == "No calm reference matches this acquisition configuration"


def test_reference_uses_its_configuration_training_dates(reference):
    path = calm.artifact_root() / "active.json"
    manifest = json.loads(path.read_text())
    config = manifest["configurations"][calm.fingerprint(reference[0])]
    config.update(training_start=100, training_end=500)
    stat = path.stat()
    path.write_text(json.dumps(manifest))
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    info, arrays = calm.reference(reference[0])
    assert arrays is not None
    assert (info["training_start"], info["training_end"]) == (100, 500)


def test_manifest_retains_separate_fitting_dates_for_each_configuration():
    def config(path, epoch):
        return dict(fit_frames=[[path, 0]], sources=[dict(path=path, frame=0, epoch=epoch),
                                                    dict(path=path, frame=1, epoch=epoch+10)])
    manifest = dict(training_start=0, training_end=5000,
                    configurations={"old": config("old.hdf5", 100), "new": config("new.hdf5", 1000)})
    result = finalize_manifest(manifest)
    assert (result["training_start"], result["training_end"]) == (100, 1010)
    assert result["configurations"]["old"]["training_end"] == 110
    assert result["configurations"]["new"]["training_start"] == 1000
    assert (result["requested_start"], result["requested_end"]) == (0, 5000)


@pytest.fixture
def trimmed_recordings(tmp_path, monkeypatch):
    monkeypatch.setenv('DAS_ARCHIVE_ROOT', str(tmp_path))
    records = []
    for name, channels in [('source', [0, 8, 16, 100, 108, 116]), ('target', [0, 8, 100, 108])]:
        path = tmp_path / (name + '.hdf5')
        with h5py.File(path, 'w') as f:
            f['data'] = np.zeros((10, len(channels)))
            for key, value in dict(channels=channels, time=1000., dt=.002, unit='rad/(m*s)', dataScale=1.,
                                   gaugeLength=16., instrumentSerial=152, missingSamples=np.array([], dtype=int)).items():
                f['header/' + key] = value
            f['demodSpec/roiStart'] = [0, 100]
            f['demodSpec/roiEnd'] = [16, 116] if name == 'source' else [8, 108]
            f['demodSpec/roiDec'] = [8, 8]
            f['cableSpec/sensorDistances'] = [ch if ch < 100 else ch-100 for ch in channels]
        rec = inspect_recording(path)
        rec.update(lid=1, processing='stored values × dataScale')
        records.append(rec)
    return records


def test_baseline_projection_selects_exact_channel_ids_across_roi_gaps(trimmed_recordings):
    source, target = trimmed_recordings
    assert compatible_subset(source, target).tolist() == [0, 1, 3, 4]


@pytest.mark.parametrize('field,value', [
    ('header/gaugeLength', 8.), ('header/dataScale', 2.), ('header/instrumentSerial', 153),
    ('demodSpec/roiDec', [4, 4]), ('demodSpec/roiStart', [1, 100]),
    ('demodSpec/roiEnd', [24, 108]), ('header/channels', [0, 8, 100, 112]),
    ('cableSpec/sensorDistances', [0., 8., 0., 9.]),
])
def test_baseline_projection_rejects_other_acquisition_changes(trimmed_recordings, field, value):
    source, target = trimmed_recordings
    path = stitched_signals.safe_path(target['relative_path'])
    with h5py.File(path, 'a') as f:
        del f[field]
        f[field] = value
    target.update(inspect_recording(path))
    with pytest.raises(ValueError):
        compatible_subset(source, target)
