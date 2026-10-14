"""Directory replay stays separate from genuine capture and database records."""
import json
import os
from pathlib import Path
import threading
import time

import h5py
import numpy as np
import pytest
from fastapi.testclient import TestClient

from src.Mapui import demo, live
from src.Mapui.launcher import arguments


@pytest.fixture
def directory(tmp_path, monkeypatch):
    monkeypatch.setenv("DAS_ARCHIVE_ROOT", str(tmp_path))
    monkeypatch.setenv("DAS_DEMO_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("DAS_METRIC_CACHE", str(tmp_path / "metrics"))
    monkeypatch.setenv("DAS_LIVE_SNAPSHOT", str(tmp_path / "snapshot.json"))
    monkeypatch.delenv("DAS_DEMO_DIR", raising=False)
    monkeypatch.delenv("DAS_LIVE_ZMQ_BIND", raising=False)
    path = tmp_path / "example.hdf5"
    with h5py.File(path, "w") as f:
        f["data"] = np.random.default_rng(0).normal(size=(5000, 3))
        for key, value in dict(channels=[0, 4, 8], dt=.002, time=1000., dataScale=2., unit="rad/(m*s)",
                               missingSamples=np.array([], dtype=int)).items():
            f["header/" + key] = value
    return tmp_path


def test_startup_options_and_environment(directory, monkeypatch):
    assert arguments([]).demo is None
    args = arguments(["--demo", str(directory), "--demo-interval", "8", "--demo-lid", "1"])
    assert args.demo == directory and args.demo_interval == 8 and args.demo_lid == 1
    monkeypatch.setenv("DAS_DEMO_DIR", str(directory))
    assert arguments([]).demo == directory
    assert arguments(["--no-demo"]).demo is None
    with pytest.raises(SystemExit):
        arguments(["--demo", str(directory / "absent")])
    with pytest.raises(SystemExit):
        arguments(["--demo-interval", "nan"])


def test_files_are_sorted_and_external_symlinks_excluded(directory, tmp_path):
    (directory / "001.h5").touch()
    (directory / "skip.txt").touch()
    other = directory.parent / "outside.hdf5"
    other.touch()
    (directory / "external.hdf5").symlink_to(other)
    assert [p.name for p in demo.source_files(directory)] == ["001.h5", "example.hdf5"]


def test_preparation_caches_without_verification_or_database_writes(directory, monkeypatch):
    calls = []
    def metric(recording, lid, **kwargs):
        assert not recording["time_verified"] and not recording["mapping_verified"]
        calls.append(recording["id"])
        return dict(recording_id=recording["id"], frame=0, data={"type": "FeatureCollection", "features": []})
    monkeypatch.setattr(demo, "map_metrics", metric)
    monkeypatch.setattr(demo, "rows", lambda *_: pytest.fail("Preparation must not index or write database rows"))
    path = directory / "example.hdf5"
    result = demo.prepare_file(path, 1, "test-mapping")
    assert result["acquisition_epoch"] == 1000
    assert result["recording_id"] < 0 and abs(result["recording_id"]) < 2 ** 53
    assert result["demo_has_metric"] and result["detection"]["status"] == "disabled"
    assert result["heatmap"]["status"] == "complete"
    assert demo.prepare_file(path, 1, "test-mapping") == result and len(calls) == 1
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    changed = demo.prepare_file(path, 1, "test-mapping")
    assert changed["demo_token"] != result["demo_token"] and len(calls) == 2
    remapped = demo.prepare_file(path, 1, "new-mapping")
    assert remapped["demo_token"] != changed["demo_token"]


def test_demo_status_requires_enabled_mode_and_uses_publication_age(directory, monkeypatch):
    payload = {"demo": True, "replay": True, "published_at": time.time(),
               "acquisition_epoch": 1000, "time_verified": False, "points": []}
    live.write_snapshot(payload)
    monkeypatch.delenv("DAS_DEMO_ENABLED", raising=False)
    assert live.load_snapshot()["status"] == "replay"
    monkeypatch.setenv("DAS_DEMO_ENABLED", "1")
    assert live.load_snapshot()["status"] == "demo"
    assert live.load_snapshot()["acquisition_epoch"] == 1000
    payload["published_at"] -= 40
    live.write_snapshot(payload)
    assert live.load_snapshot()["status"] == "demo_stale"
    live.write_snapshot({"demo": True, "replay": True, "published_at": time.time(), "points": [], "demo_loading": True})
    assert live.load_snapshot()["status"] == "demo_loading"


def test_metric_api_is_demo_only_and_validates_tokens(directory, monkeypatch):
    from src.Mapui.api import app
    token = "a" * 64
    demo.write_json(demo.cache_root() / f"{token}.metrics.json", {"recording_id": -1})
    with TestClient(app) as client:
        monkeypatch.delenv("DAS_DEMO_ENABLED", raising=False)
        assert client.get(f"/api/demo/metrics/{token}").status_code == 404
        monkeypatch.setenv("DAS_DEMO_ENABLED", "1")
        assert client.get("/api/demo/metrics/invalid").status_code == 404
        assert client.get(f"/api/demo/metrics/{'b' * 64}").status_code == 404
        response = client.get(f"/api/demo/metrics/{token}")
        assert response.json() == {"recording_id": -1}
        assert "immutable" in response.headers["cache-control"]
        assert client.get("/api/live").headers["cache-control"] == "no-store"


class ImmediateExecutor:
    def __init__(self, **kwargs): pass
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def submit(self, function, *args):
        class Future:
            def done(self): return True
            def result(self): return function(*args)
        return Future()


def test_loop_wraps_skips_invalid_files_and_preserves_source_time(directory, monkeypatch):
    paths = [directory / "a.hdf5", directory / "broken.hdf5", directory / "b.hdf5"]
    monkeypatch.setattr(demo, "source_files", lambda _: paths)
    monkeypatch.setattr(demo, "mapping_context", lambda *_: (1, "mapping"))
    monkeypatch.setattr(demo, "ThreadPoolExecutor", ImmediateExecutor)
    clock = [0.]
    monkeypatch.setattr(demo.time, "monotonic", lambda: clock[0])
    class Stop:
        stopped = False
        def is_set(self): return self.stopped
        def wait(self, seconds): clock[0] += seconds
    stop = Stop()
    seen = []
    def prepare(path, *_):
        if path.name == "broken.hdf5": raise ValueError("unfinished file")
        return dict(filename=path.name, points=[], acquisition_epoch=1000)
    monkeypatch.setattr(demo, "prepare_file", prepare)
    def write(payload):
        if payload.get("filename"):
            item = (payload["filename"], payload["demo_cycle"])
            if not seen or seen[-1] != item: seen.append(item)
            assert payload["demo"] and payload["replay"] and payload["acquisition_epoch"] == 1000
            if len(seen) == 3: stop.stopped = True
    monkeypatch.setattr(demo, "write_snapshot", write)
    demo.run_demo(directory, 5, stop)
    assert seen == [("a.hdf5", 1), ("b.hdf5", 1), ("a.hdf5", 2)]


def test_empty_directory_reports_waiting_instead_of_replaying_old_data(directory, monkeypatch):
    monkeypatch.setattr(demo, "source_files", lambda _: [])
    monkeypatch.setattr(demo, "mapping_context", lambda *_: (1, "mapping"))
    stop = threading.Event()
    seen = []
    def write(payload):
        seen.append(payload)
        if "No readable" in payload.get("note", ""): stop.set()
    monkeypatch.setattr(demo, "write_snapshot", write)
    demo.run_demo(directory, 5, stop)
    assert seen[-1]["demo_loading"] and seen[-1]["points"] == []
