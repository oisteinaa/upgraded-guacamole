"""Live summaries use full samples, retain gaps and never imply a class."""
import json

import h5py
import numpy as np
import pytest

from src.Mapui.live_summary import channel_groups, profile_summary, recording_summary
from src.Capture.event_detector import assess_rules


@pytest.fixture
def capture(tmp_path, monkeypatch):
    monkeypatch.setenv("DAS_ARCHIVE_ROOT", str(tmp_path))
    monkeypatch.setenv("DAS_LIVE_SNAPSHOT", str(tmp_path / "snapshot.json"))
    data = np.random.default_rng(42).normal(size=(1003, 5))
    data[:, 1] = 1000000  # offset must vanish in AC statistics
    data[505, 3] = 80
    path = tmp_path / "live.hdf5"
    with h5py.File(path, "w") as f:
        f["data"] = data
        f["header/missingSamples"] = np.array([], dtype=int)
    rec = dict(id=7, relative_path=path.name, samples=len(data), channels=[0, 4, 8, 100, 104],
               scale=2., dt=.002, size_bytes=path.stat().st_size, mtime_ns=path.stat().st_mtime_ns,
               unit="rad/(m*s)", processing="stored values × dataScale", acquisition_epoch=1781568000,
               time_verified=True, mapping_verified=False, lid=1)
    return rec, data * 2, path


def test_streamed_heatmap_matches_direct_computation(capture):
    rec, scaled, _ = capture
    rms, variance, heat = recording_summary(rec)
    np.testing.assert_allclose(rms, np.sqrt(np.mean(scaled ** 2, axis=0)))
    np.testing.assert_allclose(variance, np.var(scaled, axis=0), atol=1e-8)
    bounds = np.rint(np.array(heat["time_edges"]) / rec["dt"]).astype(int)
    groups, edges = channel_groups(rec["channels"])
    assert len(heat["values"]) <= 120 and len(groups) <= 300
    assert heat["channel_edges"] == edges
    for i, (a, b) in enumerate(zip(bounds[:-1], bounds[1:])):
        ac = np.std(scaled[a:b], axis=0)
        for j, group in enumerate(groups):
            if group is None:
                assert heat["values"][i][j] is None
                assert heat["peak_channels"][i][j] is None
            else:
                assert heat["values"][i][j] == pytest.approx(max(ac[group]), abs=1e-8)
                assert heat["peak_channels"][i][j] in [rec["channels"][c] for c in group]
    assert bounds[-1] == len(scaled) and len(set(np.diff(bounds))) == 2


def test_profile_preserves_peaks_and_explicit_gaps():
    channels = list(range(0, 8000, 4)) + [9000, 9004]
    values = np.ones(len(channels))
    values[431] = 100
    values[433] = 0
    profile = profile_summary(channels, values)
    assert 100 in profile["values"] and 0 in profile["values"]
    assert None in profile["channels"] and len(profile["channels"]) <= 1200
    groups, _ = channel_groups(list(reversed(channels)))
    assert len(groups) <= 300


def test_changed_capture_rejected(capture):
    rec, _, path = capture
    path.touch()
    with pytest.raises(ValueError, match="changed"):
        recording_summary(rec)


def test_nonfinite_capture_rejected(capture):
    rec, _, path = capture
    with h5py.File(path, "r+") as f:
        f["data"][2, 2] = np.nan
    rec["mtime_ns"] = path.stat().st_mtime_ns
    with pytest.raises(ValueError, match="Nonfinite"):
        recording_summary(rec)


def rule(rec, channels, limit=10):
    return dict(name="Calibrated test rule", lid=1, unit=rec["unit"],
                processing=rec["processing"], channels=channels, rms_limit=limit)


def test_assessment_reports_coverage_and_unique_candidates(capture):
    rec, _, _ = capture
    rec["mapping_verified"] = True
    _, result = assess_rules(rec, {0: 12, 4: 3, 8: 100}, [rule(rec, [0, 4, 80]), rule(rec, [0], 11)])
    assert result["status"] == "complete"
    assert result["evaluated_channels"] == 2 and result["requested_channels"] == 3
    assert result["candidate_count"] == 1 and result["candidates"][0]["ratio"] == 1.2
    _, quiet = assess_rules(rec, {0: 3}, [rule(rec, [0])])
    assert quiet["status"] == "complete" and quiet["candidate_count"] == 0
    _, unavailable = assess_rules(rec, {0: 3}, [rule(rec, [4])])
    assert unavailable["status"] == "unavailable"


def stub_publish(monkeypatch, rec):
    from src.Mapui import live, metrics
    monkeypatch.setattr(live, "rows", lambda sql, *args: [rec] if "das_recordings" in sql else [])
    monkeypatch.setattr(metrics, "metric_frame", lambda *args: dict(
        frame_count=1, processing="test", start=0, end=2.006,
        values={"ac_rms": np.arange(5, dtype=float)}))
    return live


def test_publication_without_detection_and_roundtrip(capture, monkeypatch):
    rec, _, _ = capture
    live = stub_publish(monkeypatch, rec)
    result = live.publish_recording(rec["id"])
    assert result["detection"]["status"] == "not_configured"
    assert result["filename"] == "live.hdf5" and result["summary_version"] == 1
    loaded = live.load_snapshot()
    assert loaded["status"] == "stale"
    assert loaded["heatmap"] == result["heatmap"]


def test_detection_failure_keeps_signal_and_pending_state(capture, monkeypatch):
    from src.Capture import event_detector
    rec, _, _ = capture
    rec["mapping_verified"] = True
    live = stub_publish(monkeypatch, rec)
    def fail(*args, **kwargs):
        pending = json.loads(live.snapshot_path().read_text())
        assert pending["detection"]["status"] == "processing"
        assert pending["recording_id"] == rec["id"]
        raise ValueError("test detector failure")
    monkeypatch.setattr(event_detector, "detect_events", fail)
    result = live.publish_recording(rec["id"], rules=[], legacy_timezone="Europe/Oslo")
    assert result["detection"]["status"] == "failed"
    assert result["heatmap"]["status"] == "complete"
    assert live.load_snapshot()["detection"]["status"] == "failed"


def test_unverified_capture_does_not_attempt_detection(capture, monkeypatch):
    from src.Capture import event_detector
    rec, _, _ = capture
    live = stub_publish(monkeypatch, rec)
    def unexpected(*args, **kwargs):
        pytest.fail("Unverified alignment must not reach detection")
    monkeypatch.setattr(event_detector, "detect_events", unexpected)
    result = live.publish_recording(rec["id"], rules=[rule(rec, [0])], legacy_timezone="Europe/Oslo")
    assert result["detection"]["status"] == "unavailable"
    assert result["heatmap"]["status"] == "complete"
