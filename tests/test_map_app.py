"""Run integration tests only against the disposable sensnetdb_test clone."""

import os

import h5py
import numpy as np
import pytest
from fastapi.testclient import TestClient

from src.Mapui.signals import envelope, inspect_recording, read_signal


def test_peak_envelope_preserves_transient_and_tail():
    values = np.zeros(10003)
    values[5001] = 123
    values[5002] = -111
    values[-1] = 42
    x, y = envelope(values, 100, 0.002, 300)
    assert max(y) == 123 and min(y) == -111 and y[-1] == 42
    assert len(x) <= 300 and x == sorted(x)
    assert x[-1] == pytest.approx((100 + 10002) * 0.002)


@pytest.fixture
def recording(tmp_path, monkeypatch):
    monkeypatch.setenv("DAS_ARCHIVE_ROOT", str(tmp_path))
    p = tmp_path / "sample.hdf5"
    dt = 0.002
    t = np.arange(5000) * dt
    with h5py.File(p, "w") as f:
        f["data"] = np.column_stack(
            [np.sin(2 * np.pi * 10 * t), np.sin(2 * np.pi * 30 * t), np.ones(len(t))]
        )
        for k, v in {
            "time": 1781568000,
            "dt": dt,
            "channels": [100, 108, 999],
            "unit": "rad/(m*s)",
            "dataScale": 2,
            "missingSamples": np.array([], dtype=int),
        }.items():
            f["header/" + k] = v
    result = inspect_recording(p)
    result.update(id=1, processing="stored values × dataScale", time_verified=False)
    return p, result


def test_explicit_channel_selection_scaling_and_spectrum(recording):
    _, rec = recording
    data = read_signal(rec, 108, 0, 10, 300)
    assert len(data["x"]) <= 300
    assert data["source_samples"] == 5000
    assert data["heat_channels"] == [100, 108, 999]
    assert abs(data["frequency"][np.argmax(data["power"])] - 30) < 0.2
    assert np.mean(data["rms"]) == pytest.approx(np.sqrt(2), rel=0.08)
    assert data["unit"] == "rad/(m*s)"


def test_nonexistent_channel_is_not_column_index(recording):
    with pytest.raises(ValueError, match="not present"):
        read_signal(recording[1], 1, 0, 1)


def test_changed_file_rejected(recording):
    path, rec = recording
    path.touch()
    with pytest.raises(ValueError, match="changed"):
        read_signal(rec, 100, 0, 1)


def test_invalid_window_rejected(recording):
    with pytest.raises(ValueError, match="eight samples"):
        read_signal(recording[1], 100, 50, 1)


def test_path_traversal_rejected(recording):
    rec = dict(recording[1], relative_path="../outside.hdf5")
    with pytest.raises(ValueError, match="unavailable"):
        read_signal(rec, 100, 0, 1)


def test_missing_samples_rejected(recording):
    path, _ = recording
    with h5py.File(path, "a") as f:
        del f["header/missingSamples"]
        f["header/missingSamples"] = [5]
    with pytest.raises(ValueError, match="samples missing"):
        inspect_recording(path)


@pytest.fixture(scope="module")
def client():
    if not os.getenv("DAS_TEST_DATABASE_URL"):
        pytest.skip("Set DAS_TEST_DATABASE_URL to the disposable local clone")
    from psycopg2.extensions import parse_dsn

    dsn = os.environ["DAS_TEST_DATABASE_URL"]
    assert parse_dsn(dsn)["dbname"] == "sensnetdb_test", (
        "Refusing writes to a non-test database"
    )
    old = os.environ.get("DAS_DATABASE_URL")
    os.environ["DAS_DATABASE_URL"] = dsn
    from src.Mapui.api import app
    from src.Mapui.db import database

    with database(write=True) as cur:
        cur.execute(
            "INSERT INTO events(id,time,type,value,comment) VALUES(-2001,'2025-05-01 12:00',1,123,'UI test event') ON CONFLICT(id) DO NOTHING"
        )
    with TestClient(app) as client:
        yield client
    with database(write=True) as cur:
        cur.execute("DELETE FROM event_reviews WHERE event_id=-2001")
        cur.execute("DELETE FROM events WHERE id=-2001")
    if old is None:
        os.environ.pop("DAS_DATABASE_URL")
    else:
        os.environ["DAS_DATABASE_URL"] = old


def test_legacy_snapshot_preserved(client):
    o = client.get("/api/overview").json()
    assert o["counts"]["events"] >= 115847
    assert o["counts"]["unclassified"] >= 115847
    assert o["counts"]["masts"] == 579 and o["counts"]["spans"] == 575
    assert len(o["classes"]) == 4


def test_event_pagination_and_null_class(client):
    page = client.get("/api/events?classid=0&limit=2").json()
    assert len(page["items"]) == 2 and page["total"] >= 115847
    assert all(e["classid"] is None for e in page["items"])
    second = client.get("/api/events?classid=0&limit=2&offset=2").json()
    assert not {e["id"] for e in page["items"]} & {e["id"] for e in second["items"]}


def test_legacy_unlocated_remains_visible(client):
    assert client.get("/api/events?search=UI%20test").json()["total"] == 1
    assert client.get("/api/events?route=R06&search=UI%20test").json()["total"] == 0
    assert client.get("/api/events/-2001/signal").status_code == 404
    assert client.get("/api/map/events").json()["data"]["features"] == []


def test_atomic_review_conflict_and_revert(client):
    payload = {
        "classid": 3,
        "expected_classid": None,
        "expected_revision": 0,
        "reviewer": "Test reviewer",
        "note": "Synthetic test only",
    }
    r = client.post("/api/events/-2001/reviews", json=payload)
    assert r.status_code == 200
    d = r.json()
    assert (
        d["classid"] == 3
        and d["revision"] == 1
        and d["reviews"][0]["previous_classid"] is None
    )
    assert client.post("/api/events/-2001/reviews", json=payload).status_code == 409
    assert (
        client.get("/api/events?review=reviewed&search=UI%20test").json()["total"] == 1
    )
    payload.update(
        classid=None,
        expected_classid=3,
        expected_revision=1,
        note="Return test to unclassified",
    )
    d = client.post("/api/events/-2001/reviews", json=payload).json()
    assert d["classid"] is None and len(d["reviews"]) == 2


def test_invalid_class_does_not_mutate(client):
    old = client.get("/api/events/-2001").json()
    r = client.post(
        "/api/events/-2001/reviews",
        json={
            "classid": 32000,
            "expected_classid": old["classid"],
            "expected_revision": old["revision"],
            "reviewer": "Test",
            "note": "Invalid class",
        },
    )
    assert r.status_code == 422
    assert client.get("/api/events/-2001").json()["revision"] == old["revision"]


def test_blank_review_and_cross_origin_rejected(client):
    assert (
        client.post(
            "/api/events/-2001/reviews",
            json={"reviewer": " ", "note": " ", "expected_revision": 0},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/events/-2001/reviews",
            json={},
            headers={"Origin": "https://unrelated.example"},
        ).status_code
        == 403
    )


def test_map_geometry_and_water_uncertainty(client):
    d = client.get("/api/map").json()
    assert len(d["masts"]["features"]) == 579 and len(d["spans"]["features"]) == 575
    candidates = [
        f
        for f in d["spans"]["features"]
        if f["properties"]["water_status"] == "map_candidate"
    ]
    assert len(candidates) == 7 and all(
        f["properties"]["crosses_water"] is None for f in candidates
    )


def test_signal_endpoint_bounded_real_file(client):
    recordings = client.get("/api/recordings").json()
    assert len(recordings) == 3
    rec = recordings[0]
    r = client.get(
        f"/api/recordings/{rec['id']}/signal?channel={rec['first_channel']}&duration=2&points=200"
    )
    assert r.status_code == 200
    d = r.json()
    assert d["display_points"] <= 200 and d["source_samples"] > 900
    assert (
        client.get(f"/api/recordings/{rec['id']}/signal?channel=-1").status_code == 422
    )
    assert (
        client.get(
            f"/api/recordings/{rec['id']}/signal?channel=0&duration=700"
        ).status_code
        == 422
    )


def test_weather_has_no_future_values(client):
    at = "2025-05-01T12:00:00"
    d = client.get("/api/weather", params={"station": 1, "at": at}).json()
    assert all(row["time"] <= at for row in d["items"])
    assert (
        client.get("/api/weather", params={"station": 1, "at": at + "Z"}).status_code
        == 422
    )


def test_filters_validate_date_order(client):
    assert client.get("/api/events?start=2025-06-01&end=2025-05-01").status_code == 422
    assert client.get("/api/events?limit=99999").status_code == 422


def test_detection_refuses_unverified_alignment():
    from src.Capture.event_detector import detect_events

    with pytest.raises(ValueError, match="verified"):
        detect_events(
            {"time_verified": False, "mapping_verified": True, "lid": 1},
            {},
            [],
            "Europe/Oslo",
        )


def test_detection_rejects_mismatched_signal_units():
    from src.Capture.event_detector import detect_events

    rec = {
        "time_verified": True,
        "mapping_verified": True,
        "lid": 1,
        "acquisition_epoch": 1781568000,
        "processing": "stored values × dataScale",
        "unit": "rad/(m*s)",
    }
    with pytest.raises(ValueError, match="unit/processing"):
        detect_events(
            rec,
            {},
            [{"unit": "old integrated metric", "processing": "old"}],
            "Europe/Oslo",
        )


def test_detection_is_idempotent_and_retains_null_class(client):
    from src.Capture.event_detector import detect_events
    from src.Mapui.db import database, rows

    with database(write=True) as cur:
        cur.execute(
            "INSERT INTO das_recordings(id,relative_path,acquisition_epoch,dt,samples,channels,unit,scale,size_bytes,mtime_ns,lid,time_verified,mapping_verified) VALUES (-20,'test-only.hdf5',1781568000,.002,100,ARRAY[0],'rad/(m*s)',1,1,1,1,true,true)"
        )
    rec = rows("SELECT * FROM das_recordings WHERE id=-20")[0]
    rule = {
        "name": "Test candidate",
        "unit": rec["unit"],
        "processing": rec["processing"],
        "rms_limit": 10,
        "lid": 1,
        "channels": [0],
    }
    try:
        created = detect_events(rec, {0: 12}, [rule], "Europe/Oslo")
        assert len(created) == 1
        assert detect_events(rec, {0: 12}, [rule], "Europe/Oslo") == []
        event = client.get(f"/api/events/{created[0]}").json()
        assert event["classid"] is None and event["context"]["alignment_verified"]
        assert event["context"]["recording_id"] == -20
        assert event["time"].startswith("2026-06-16T02:00:00")
    finally:
        with database(write=True) as cur:
            cur.execute("SELECT event_id FROM event_context WHERE recording_id=-20")
            ids = [r["event_id"] for r in cur.fetchall()]
            cur.execute("DELETE FROM event_context WHERE recording_id=-20")
            cur.execute("DELETE FROM events WHERE id=ANY(%s)", (ids,))
            cur.execute("DELETE FROM das_recordings WHERE id=-20")


def test_live_replay_is_not_live_and_reduction_preserves_peaks(tmp_path, monkeypatch):
    import json
    import time

    from src.Mapui.live import load_snapshot

    path = tmp_path / "snapshot.json"
    monkeypatch.setenv("DAS_LIVE_SNAPSHOT", str(path))
    points = [{"channel": i, "rms": 1.0} for i in range(10000)]
    points[3333]["rms"] = 1000
    path.write_text(
        json.dumps(
            {
                "points": points,
                "published_at": time.time(),
                "acquisition_epoch": time.time(),
                "replay": True,
                "time_verified": True,
            }
        )
    )
    d = load_snapshot(200)
    assert d["status"] == "replay" and len(d["points"]) <= 200
    assert d["source_points"] == 10000
    assert max(p["rms"] for p in d["points"]) == 1000


def test_live_fresh_publication_of_old_capture_is_stale(tmp_path, monkeypatch):
    import json
    import time

    from src.Mapui.live import load_snapshot

    path = tmp_path / "snapshot.json"
    monkeypatch.setenv("DAS_LIVE_SNAPSHOT", str(path))
    path.write_text(
        json.dumps(
            {
                "points": [],
                "published_at": time.time(),
                "acquisition_epoch": time.time() - 1000,
                "replay": False,
                "time_verified": True,
            }
        )
    )
    assert load_snapshot()["status"] == "stale"


def test_database_keeps_legacy_insert_and_class_foreign_key(client):
    import psycopg2

    from src.Mapui.db import database

    with database(write=True) as cur:
        cur.execute(
            "INSERT INTO events(id,type,value,comment) VALUES(-2100,1,12,'Legacy insert probe') RETURNING classid"
        )
        assert cur.fetchone()["classid"] is None
        cur.execute("DELETE FROM events WHERE id=-2100")
    with (
        pytest.raises(psycopg2.errors.ForeignKeyViolation),
        database(write=True) as cur,
    ):
        cur.execute(
            "INSERT INTO events(id,type,value,comment,classid) VALUES(-2100,1,12,'Invalid class probe',32000)"
        )


def test_verified_event_window_reads_exact_recording(client):
    from src.Mapui.db import database, rows

    original = rows("SELECT * FROM das_recordings WHERE id=1")[0]
    try:
        with database(write=True) as cur:
            cur.execute(
                "UPDATE das_recordings SET time_verified=true,mapping_verified=true,lid=1 WHERE id=1"
            )
            cur.execute(
                "INSERT INTO events(id,type,value,comment) VALUES(-2101,1,12,'Synthetic alignment test')"
            )
            cur.execute(
                "INSERT INTO event_context(event_id,recording_id,start_sample,stop_sample,lid,channel,alignment_verified,evidence) VALUES(-2101,1,100,500,1,0,true,'Synthetic test only')"
            )
        result = client.get("/api/events/-2101/signal?before=0&after=0")
        assert result.status_code == 200
        data = result.json()
        assert data["source_samples"] == 400
        assert data["start"] == pytest.approx(100 * original["dt"])
        assert data["event_end"] == pytest.approx(500 * original["dt"])
        assert client.get("/api/events/-2101/signal?before=nan").status_code == 422
    finally:
        with database(write=True) as cur:
            cur.execute("DELETE FROM event_context WHERE event_id=-2101")
            cur.execute("DELETE FROM events WHERE id=-2101")
            cur.execute(
                "UPDATE das_recordings SET time_verified=%s,mapping_verified=%s,lid=%s WHERE id=1",
                (
                    original["time_verified"],
                    original["mapping_verified"],
                    original["lid"],
                ),
            )


def test_metric_endpoint_maps_both_sampling_grids_and_keeps_original_ids(client):
    d = client.get("/api/recordings/1/metrics?lid=1").json()
    assert d["mapping"]["exact"] == 17010
    assert d["mapping"]["interpolated"] == 8224
    assert d["mapping"]["unmatched_recording"] == 2
    assert d["start_sample"] == 0 and d["stop_sample"] == 4902
    assert d["complete"]
    p = next(
        f["properties"]
        for f in d["data"]["features"]
        if f["properties"]["recording_channel"] == 69004
    )
    assert (
        p["mapped_channel"] is None
        and p["lower_channel"] == 69003
        and p["upper_channel"] == 69007
    )
    assert p["mapping"] == "interpolated"
    assert (
        client.get("/api/recordings/1/metrics?lid=1&metric=variance")
        .json()["unit"]
        .endswith("²")
    )
    assert (
        client.get("/api/recordings/1/metrics?lid=1&low=10&high=1").status_code == 422
    )
    assert client.get("/api/recordings/1/metrics?lid=1&frame=999").status_code == 422
    assert client.get("/api/recordings/1/metrics?lid=999").status_code == 422


def test_fibre_geometry_retains_all_positions_and_runs(client):
    d = client.get("/api/fibre?lid=1").json()
    assert len(d["features"]) == 25235
    assert {f["properties"]["run"] for f in d["features"]} == {"1:0", "1:69003"}


def test_channel_width_uses_ids_and_inclusive_bounds(recording):
    _, rec = recording
    rec = dict(rec, channels=[1250, 750, 1400])
    data = read_signal(rec, 1000, 0, 1, channel_count=500)
    assert data['channel_bounds'] == [750, 1250]
    assert data['heat_channels'] == [1250, 750]
    assert data['channel'] == 750
    assert len(data['heat']) == 2
    # Selected IDs retain the correct file columns even in descending order.
    assert np.mean(data['heat'][1]) > 0


def test_channel_range_excludes_gaps_and_clips_to_recording(recording):
    _, rec = recording
    data = read_signal(rec, 108, 0, 1, channel_count=500)
    assert data['heat_channels'] == [100, 108]
    with pytest.raises(ValueError, match='No recorded channels'):
        read_signal(rec, 500, 0, 1, channel_count=10)
    data = read_signal(rec, 500, 0, 1, channel_bounds=[108, 999])
    assert data['heat_channels'] == [108, 999]
    assert data['channel'] == 108


def test_span_signal_validates_mapping_and_uses_endpoint_bounds(recording, monkeypatch):
    from src.Mapui import api as module
    rec = dict(recording[1], lid=1, mapping_verified=True)
    monkeypatch.setattr(module, 'get_recording', lambda _: rec)
    monkeypatch.setattr(module, 'rows', lambda *args: [dict(
        from_lid=1, to_lid=1, from_channel=999, to_channel=108)])
    result = module.signal(1, 100, 0, 1, 1600, None, 7)
    assert result['heat_channels'] == [108, 999]
    rec['mapping_verified'] = False
    with pytest.raises(module.HTTPException) as error:
        module.signal(1, 100, 0, 1, 1600, None, 7)
    assert error.value.status_code == 422


def test_spatial_metrics_follow_selected_channels_and_remove_dc(recording):
    path, rec = recording
    with h5py.File(path, 'a') as f:
        f['data'][:, 1] = f['data'][:, 1] * 3 + 100
    rec.update(inspect_recording(path))
    data = read_signal(rec, 500, 0, 10, channel_bounds=[108, 999])
    assert data['heat_channels'] == [108, 999]
    np.testing.assert_allclose(data['channel_variance'], [[18, 0]], atol=1e-10)
    np.testing.assert_allclose(data['channel_rms'], [[np.sqrt(18), 0]], atol=1e-10)
    zoom = read_signal(rec, 500, 2, 1, channel_bounds=[108, 999])
    assert zoom['channel_variance'] == data['channel_variance']
    assert zoom['trend_start'] == 0
    assert zoom['trend_window_seconds'] == 10
