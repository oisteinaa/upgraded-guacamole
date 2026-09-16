import h5py
import numpy as np
import pytest

from src.Mapui.metrics import (
    calculate_metrics,
    frame_bounds,
    interpolation_regions,
    metric_frame,
    resolve_positions,
)
from src.Mapui.signals import inspect_recording, read_signal


def test_metrics_remove_dc_and_keep_units():
    t = np.arange(10000) * 0.001
    x = 123 + 2 * np.sin(2 * np.pi * 10 * t)
    m = calculate_metrics(x[:, None], 0.001, 8, 12)
    assert m["ac_rms"][0] == pytest.approx(np.sqrt(2))
    assert m["variance"][0] == pytest.approx(2)
    assert m["peak"][0] == pytest.approx(2)
    assert m["band_rms"][0] == pytest.approx(np.sqrt(2), rel=0.02)
    outside = calculate_metrics(x[:, None], 0.001, 30, 40)
    assert outside["band_rms"][0] < 0.001


def test_impulse_peak_survives_and_constant_is_quiet():
    x = np.full((5000, 2), 200.0)
    x[1234, 0] += 100
    m = calculate_metrics(x, 0.002)
    assert m["peak"][0] == pytest.approx(99.98)
    assert m["ac_rms"][1] == 0 and m["band_rms"][1] == 0


@pytest.mark.parametrize(
    "low,high", [(0, 10), (10, 1), (1, 251), (0.01, 1), (1, 1.001), (float("nan"), 10)]
)
def test_invalid_spectral_bands(low, high):
    with pytest.raises(ValueError):
        calculate_metrics(np.zeros((5000, 2)), 0.002, low, high)


def test_frame_bounds_fixed_rounding_and_partial():
    r = {"samples": 10200, "dt": 0.00204}
    assert frame_bounds(r, 0) == (0, 4902, 4902, 3)
    assert frame_bounds(r, 1) == (4902, 9804, 4902, 3)
    assert frame_bounds(r, 2) == (9804, 10200, 4902, 3)
    with pytest.raises(ValueError):
        frame_bounds(r, 3)


@pytest.fixture
def recorded(tmp_path, monkeypatch):
    monkeypatch.setenv("DAS_ARCHIVE_ROOT", str(tmp_path))
    monkeypatch.setenv("DAS_METRIC_CACHE", str(tmp_path / "cache"))
    path = tmp_path / "test.hdf5"
    t = np.arange(12000) * 0.002
    with h5py.File(path, "w") as f:
        f["data"] = np.column_stack(
            [10 + np.sin(2 * np.pi * 5 * t), 100 + 3 * np.sin(2 * np.pi * 15 * t)]
        )
        for k, v in {
            "time": 1781568000,
            "dt": 0.002,
            "channels": [0, 4],
            "dataScale": 1,
            "unit": "rad/(m*s)",
            "missingSamples": np.array([], dtype=int),
        }.items():
            f["header/" + k] = v
    r = inspect_recording(path)
    r.update(id=99, processing="stored values × dataScale", time_verified=False)
    return path, r


def test_cache_and_frame_use_source_samples(recorded):
    _, r = recorded
    a = metric_frame(r, 0)
    b = metric_frame(r, 0)
    assert a["start_sample"] == 0 and a["stop_sample"] == 5000
    assert a["values"]["ac_rms"][1] == pytest.approx(3 / np.sqrt(2))
    np.testing.assert_array_equal(a["values"]["ac_rms"], b["values"]["ac_rms"])
    assert not metric_frame(r, 2)["complete"]


def test_plot_zoom_does_not_change_rms_or_variance(recorded):
    _, r = recorded
    full = read_signal(r, 0, 0, 10)
    zoom = read_signal(r, 0, 2, 1)
    assert full["rms"] == zoom["rms"]
    assert full["variance"] == zoom["variance"]
    assert full["trend_time"] == zoom["trend_time"]


def point(channel, lat=68.0, lon=14.0, run="1:69003"):
    return {
        "channel": channel,
        "lid": 1,
        "latitude": lat,
        "longitude": lon,
        "gid": None,
        "distance": channel - 69000,
        "run": run,
    }


def test_sampling_phase_interpolates_coordinates_not_signal_indices():
    positions = [
        point(69003, lon=14.0),
        point(69007, lon=14.00004),
        point(69011, lon=14.00008),
    ]
    rec = {"channels": [69000, 69004, 69008, 69012]}
    regions = [{"start": 69000, "end": 69012, "step": 4, "native_spacing_m": 1}]
    resolved, c = resolve_positions(rec, positions, regions)
    assert [r["recording_channel"] for r in resolved] == [69004, 69008]
    assert resolved[0]["longitude"] == pytest.approx(14.00001)
    assert resolved[0]["mapped_channel"] is None
    assert (
        resolved[0]["lower_channel"] == 69003 and resolved[0]["upper_channel"] == 69007
    )
    assert c["outside"] == 2 and c["interpolated"] == 2


def test_missing_origin_evidence_does_not_guess_offset():
    resolved, c = resolve_positions(
        {"channels": [69004]}, [point(69003), point(69007)], []
    )
    assert resolved == [] and c["unresolved"] == 1


def test_no_interpolation_across_gap_or_large_geographic_jump():
    regions = [{"start": 69000, "end": 69020, "step": 4, "native_spacing_m": 1}]
    for positions in [
        [point(69003), point(69011)],
        [point(69003), point(69007, lon=15.0)],
    ]:
        resolved, c = resolve_positions({"channels": [69004]}, positions, regions)
        assert not resolved and c["gap"] == 1


def test_acquisition_origin_proof_required(recorded):
    path, r = recorded
    assert interpolation_regions(r, [point(0), point(4), point(8)]) == []
    with h5py.File(path, "a") as f:
        f["demodSpec/roiStart"] = [69000]
        f["demodSpec/roiEnd"] = [69012]
        f["demodSpec/roiDec"] = [4]
        f["cableSpec/sensorDistances"] = [0.0, 4.0]
    positions = [point(69003), point(69007), point(69011)]
    assert len(interpolation_regions(r, positions)) == 1
    positions[0]["distance"] = 0.0
    assert interpolation_regions(r, positions) == []
