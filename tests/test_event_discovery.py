import argparse
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from unittest.mock import MagicMock

import h5py
import numpy as np

from src.Capture import event_discovery as discovery


class DiscoveryTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.archive = self.root / "archive"
        self.archive.mkdir()
        self.output = self.root / "output"

    def recording(self, name="first.hdf5", start=1700000000., seconds=4, channels=128, dt=.0025):
        path = self.archive / name
        with h5py.File(path, "w") as f:
            time = np.arange(round(seconds / dt)) * dt
            signal = 200 * np.sin(2 * np.pi * 2 * time[:, None] + np.arange(channels)[None, :] / 10)
            f["data"] = signal.astype(np.int16)
            for key, value in dict(dt=dt, time=start, dataScale=.01, channels=np.arange(channels)*4,
                                   missingSamples=np.array([], dtype=int), unit="rad/(m*s)",
                                   name="phase rate per distance", gaugeLength=8., spatialUnwrRange=3000.,
                                   sensitivities=[100.], timeSynchronized=2).items():
                f[f"header/{key}"] = value
            f["demodSpec/roiDec"] = [4, 4]
        return path

    def index(self):
        return discovery.index_archive(self.archive, self.output)

    def arguments(self, **overrides):
        values = dict(index=str(self.output / "index.json"), output=str(self.output),
                      window_seconds=1., blocks=4, channels_per_block=32, max_windows=120,
                      seed=42, weather_csv=None, weather_dsn_env=None, weather_timezone=None,
                      confirm_unix_time=False, weather_max_age=7200., station=None)
        values.update(overrides)
        return argparse.Namespace(**values)

    def test_index_rejects_bad_metadata_and_source_output(self):
        good = self.recording()
        bad = self.recording("bad.hdf5")
        with h5py.File(bad, "r+") as f:
            del f["header/channels"]
        index = self.index()
        self.assertEqual([r["path"] for r in index["files"]], [str(good)])
        self.assertEqual(len(index["skipped"]), 1)
        with self.assertRaises(ValueError):
            discovery.index_archive(self.archive, self.archive / "results")

    def test_block_selection_preserves_gaps(self):
        config = dict(channels=[*range(0, 256, 4), *range(1000, 1256, 4)], roi_dec=[4, 4])
        blocks = discovery.channel_blocks(config, 16, 32)
        self.assertEqual(blocks, [(0, 32), (32, 64), (64, 96), (96, 128)])
        for lo, hi in blocks:
            self.assertTrue(np.all(np.diff(config["channels"][lo:hi]) == 4))

    def test_cross_file_window_and_bounded_scaled_reads(self):
        self.recording(seconds=1)
        self.recording("second.hdf5", start=1700000001.001, seconds=1)
        index = self.index()
        windows, skipped, boundaries = discovery.make_windows(index, 2.)
        self.assertEqual(len(windows), 1)
        self.assertTrue(boundaries[0]["joined"])
        self.assertEqual(len(windows[0]["refs"]), 2)
        config = index["configurations"][windows[0]["config"]]
        original = h5py.Dataset.__getitem__
        reads = []
        def observe(dataset, key):
            if dataset.name == "/data":
                reads.append(key)
            return original(dataset, key)
        with patch.object(h5py.Dataset, "__getitem__", observe):
            signal = discovery.read_signal(windows[0], config, 32, 64)
        self.assertEqual(signal.shape, (800, 32))
        self.assertTrue(all(key[1] == slice(32, 64) for key in reads))
        self.assertLessEqual(abs(signal).max(), 2.)
        self.assertEqual(len(reads), 2)

    def test_gaps_and_changed_config_are_not_joined(self):
        self.recording(seconds=1)
        self.recording("second.hdf5", start=1700000001.1, seconds=1)
        windows, skipped, boundaries = discovery.make_windows(self.index(), 2.)
        self.assertEqual(windows, [])
        self.assertFalse(boundaries[0]["joined"])
        self.assertEqual(len(skipped), 2)
        with h5py.File(self.archive / "second.hdf5", "r+") as f:
            f["header/time"][()] = 1700000001.
            f["header/dataScale"][()] = .02
        windows, skipped, boundaries = discovery.make_windows(self.index(), 2.)
        self.assertEqual(windows, [])
        self.assertFalse(boundaries[0]["joined"])

    def test_spectral_peak_and_detrending(self):
        time = np.arange(24000) / 400
        signal = 3*np.sin(2*np.pi*2*time) + .2*time + 10
        values = discovery.features(signal[:, None], 1/400)
        self.assertAlmostEqual(values["dominant_hz"], 2., places=2)
        self.assertAlmostEqual(values["rms"], 3/np.sqrt(2), places=2)
        self.assertGreater(values["power_1_3_hz"], .999)

    def test_weather_causality_missing_stale_and_timezone(self):
        rows = [dict(lid=1, variable="temperature", time=t, source_time=str(t), value=t) for t in (10, 30)]
        weather = discovery.Weather(rows, 10)
        self.assertIsNone(weather.at(9)["1"]["temperature"]["value"])
        self.assertEqual(weather.at(15)["1"]["temperature"]["value"], 10)
        self.assertTrue(weather.at(25)["1"]["temperature"]["stale"])
        self.assertIsNone(weather.at(25)["1"]["humidity"]["value"])
        for value in ("2026-10-25T02:30:00", "2026-03-29T02:30:00"):
            with self.assertRaises(ValueError):
                discovery.epoch(value, "Europe/Oslo")
        self.assertEqual(discovery.epoch("2026-06-16T02:00:00", "Europe/Oslo"),
                         discovery.epoch("2026-06-16T00:00:00Z"))
        with self.assertRaises(ValueError):
            discovery.epoch("2026-06-16T02:00:00")

    def test_weather_import_requires_confirmation(self):
        weather = self.root / "weather.csv"
        weather.write_text("lid,time,variable,value\n1,2026-06-16T02:00:00,temp,10\n")
        with self.assertRaises(ValueError):
            discovery.load_weather(self.arguments(weather_csv=str(weather)), [])
        rows, status = discovery.load_weather(self.arguments(weather_csv=str(weather),
            confirm_unix_time=True, weather_timezone="Europe/Oslo"), [])
        self.assertEqual(rows[0]["variable"], "temperature")

    def test_database_weather_is_read_only_and_bounded(self):
        driver = MagicMock()
        connection = driver.connect.return_value
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.__iter__.return_value = iter([(1, "2026-06-16 02:00:00", "temp", 10.)])
        args = self.arguments(weather_dsn_env="TEST_DISCOVERY_DSN", confirm_unix_time=True,
                              weather_timezone="Europe/Oslo")
        with patch.dict("sys.modules", {"psycopg2": driver}), patch.dict("os.environ", {"TEST_DISCOVERY_DSN": "dbname=test"}):
            rows, status = discovery.load_weather(args, [dict(start=1781568000.)])
        connection.set_session.assert_called_once_with(readonly=True, autocommit=False)
        sql, parameters = cursor.execute.call_args.args
        self.assertIn("WHERE o.time >= %s AND o.time <= %s", sql)
        self.assertEqual(len(parameters), 2)
        connection.rollback.assert_called_once()
        connection.close.assert_called_once()
        self.assertEqual(rows[0]["value"], 10.)

    def test_sampling_is_balanced_and_deterministic(self):
        rows = []
        for time in range(20):
            for name, value in (("temperature", -1 if time < 15 else 10), ("wind_speed", 2)):
                rows.append(dict(lid=1, variable=name, time=time, source_time=str(time), value=value))
        weather = discovery.Weather(rows, 10)
        windows = [dict(start=i) for i in range(20)]
        a = discovery.select_windows(windows, weather, 6, 42, 1)
        b = discovery.select_windows(windows, weather, 6, 42, 1)
        self.assertEqual(a, b)
        self.assertEqual(sum(r["weather_stratum"].startswith("cold") for r in a), 3)

    def test_end_to_end_resume_and_verified_export(self):
        for i in range(3):
            self.recording(f"{i}.hdf5", start=1700000000.+i*4)
        self.index()
        first = discovery.analyze(self.arguments())
        original = (self.output / "features.csv").read_bytes()
        with patch.object(discovery, "read_signal", side_effect=AssertionError("Should reuse cache")):
            second = discovery.analyze(self.arguments())
        self.assertEqual(first["feature_rows"], 48)
        self.assertEqual(second["reused_feature_rows"], 48)
        self.assertEqual(original, (self.output / "features.csv").read_bytes())
        with (self.output / "review.csv").open() as stream:
            rows = list(csv.DictReader(stream))
        rows[0]["label"] = "Normal Operations"
        discovery.write_csv(self.output / "review.csv", rows)
        with self.assertRaises(ValueError):
            discovery.export_review(self.output / "review.csv", self.output / "labels.csv")
        rows[0]["label_verified"] = "true"
        discovery.write_csv(self.output / "review.csv", rows)
        self.assertEqual(discovery.export_review(self.output / "review.csv", self.output / "labels.csv"), 1)
        discovery.analyze(self.arguments())
        with (self.output / "review.csv").open() as stream:
            preserved = {row["window_id"]: row for row in csv.DictReader(stream)}
        self.assertEqual(preserved[rows[0]["window_id"]]["label_verified"], "true")
        with h5py.File(self.archive / "0.hdf5", "r+") as f:
            f["data"][0, 0] = 123
        changed = discovery.analyze(self.arguments())
        self.assertLess(changed["reused_feature_rows"], 48)
        self.assertTrue(any("changed" in s["reason"] for s in changed["skipped"]))

    def test_multifile_review_export_keeps_session(self):
        self.recording(seconds=1)
        self.recording("second.hdf5", start=1700000001., seconds=1)
        self.index()
        discovery.analyze(self.arguments(window_seconds=2.))
        with (self.output / "review.csv").open() as stream:
            row = next(csv.DictReader(stream))
        row.update(label="Wind Galloping", label_verified="true")
        discovery.write_csv(self.output / "review.csv", [row])
        labels = self.output / "labels.csv"
        self.assertEqual(discovery.export_review(self.output / "review.csv", labels), 2)
        with labels.open() as stream:
            exported = list(csv.DictReader(stream))
        self.assertEqual(exported[0]["group"], exported[1]["group"])

    def test_small_dataset_does_not_fit(self):
        artifact, reason = discovery.learn([dict(rms=1)]*9, ["rms"], 42)
        self.assertIsNone(artifact)
        self.assertIn("Fewer than ten", reason)


if __name__ == "__main__":
    unittest.main()
