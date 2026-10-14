"""End-to-end fixtures with independent binary decoding (no writer imports)."""
import csv
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import tempfile
import time
import unittest
from datetime import datetime, timezone
import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BIN = Path(os.getenv('TRANSCRIBER_BIN', ROOT / 'target/debug/rust_transcriber'))
EPOCH = 1781568000


def h5(path, start=EPOCH, samples=1000, channels=(0, 4, 50000), dt=.01, scale=.25, missing=(), sync=2, base=0):
    data = (np.arange(samples, dtype=np.int32)[:, None] + np.arange(len(channels))[None, :] * 10000 + base).astype(np.int32)
    with h5py.File(path, 'w') as f:
        f['data'] = data
        for key, value in dict(time=start, dt=dt, channels=np.array(channels, dtype='i8'), dataScale=scale,
                               unit=np.bytes_('rad/(m*s)'), missingSamples=np.array(missing, dtype='i4'), timeSynchronized=sync).items():
            f['header/' + key] = value
    return data * scale


def segy(path):
    data = path.read_bytes()
    assert data[:3] == b'C01'
    assert struct.unpack_from('>H', data, 3224)[0] == 5
    assert struct.unpack_from('>H', data, 3500)[0] == 256
    assert struct.unpack_from('>H', data, 3502)[0] == 0
    traces = []
    pos = 3600
    while pos < len(data):
        header = data[pos:pos + 240]
        n, dt = struct.unpack_from('>HH', header, 114)
        samples = np.frombuffer(data, '>f4', n, pos + 240).copy()
        traces.append(dict(n=n, dt=dt, channel=struct.unpack_from('>I', header, 228)[0],
                           time=struct.unpack_from('>q', header, 232)[0], header=header, data=samples))
        pos += 240 + 4 * n
    assert pos == len(data)
    return traces


def segd(path):
    data = path.read_bytes()
    assert data[4:9] == b'SD3.1'
    pos, records = 128, []
    while pos < len(data):
        assert data[pos + 2:pos + 4] == bytes.fromhex('8058')
        assert data[pos + 42:pos + 44] == b'\x03\x01'
        assert data[pos + 27:pos + 29] == b'\x01\x01'
        timestamp, size, dsize, hsize = struct.unpack_from('>qQQI', data, pos + 64)
        assert size == dsize
        extra = data[pos + 11] >> 4
        if extra == 15:
            extra = struct.unpack_from('>H', data, pos + 54)[0]
        channel_set = pos + (1 + extra) * 32
        assert data[channel_set + 31] == 0x30
        assert data[channel_set + 63] == 0x31
        assert data[channel_set + 95] == 0x32
        n = struct.unpack_from('>I', data, channel_set + 12)[0]
        count = int.from_bytes(data[channel_set + 20:channel_set + 23], 'big')
        dt = int.from_bytes(data[channel_set + 23:channel_set + 26], 'big')
        assert data[channel_set + 27] == 5
        assert data[channel_set + 28] == 3
        assert data[channel_set + 4:channel_set + 12] == bytes(8)
        p, traces = pos + hsize, []
        for _ in range(count):
            nex = data[p + 9]
            assert nex == 5
            ns = struct.unpack_from('>I', data, p + 44)[0]
            assert ns == n
            assert data[p + 51] == 0x40
            assert data[p + 83] == 0x42
            assert data[p + 115] == 0x50
            assert data[p + 147] == 0x51
            assert data[p + 179] == 0x52
            channel = int.from_bytes(data[p + 23:p + 26], 'big')
            start = struct.unpack_from('>q', data, p + 52)[0]
            latitude, longitude = struct.unpack_from('>dd', data, p + 116)
            samples = np.frombuffer(data, '>f4', n, p + 20 + nex * 32).copy()
            traces.append(dict(channel=channel, time=start, latitude=latitude, longitude=longitude, data=samples))
            p += 20 + nex * 32 + 4 * n
        assert p == pos + size
        records.append(dict(time=timestamp, n=n, dt=dt, traces=traces))
        pos += size
    assert pos == len(data)
    return records


class Conversion(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.inputs = self.root / 'input'
        self.inputs.mkdir()
        self.csv = self.root / 'receivers.csv'
        self.csv.write_text('lid,channel,latitude,longitude,distance,gid\n1,0,68.1,14.2,0,5\n1,4,68.2,14.3,4,5\n1,50000,68.3,14.4,50,8\n')
        self.out = self.root / 'output'

    def tearDown(self):
        self.temp.cleanup()

    def command(self, *args):
        return [str(BIN), '--input', str(self.inputs), '--receivers-csv', str(self.csv), '--lid', '1', '--output', str(self.out), *args]

    def run_cli(self, *args, ok=True):
        result = subprocess.run(self.command(*args), text=True, capture_output=True)
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
        return result

    def navigation(self, times):
        path = self.root / 'shots.p111'
        with path.open('w') as f:
            w = csv.writer(f)
            w.writerow(['H', 'P1/11 legacy fixture'])
            for i, stamp in enumerate(times):
                row = ['0'] * 27
                row[0], row[3], row[5], row[6], row[7], row[9] = 'S1', '101', str(200 + i), '1', stamp, 'S1'
                row[12], row[13], row[14], row[26] = '14.2', '68.1', '2', '100'
                w.writerow(row)
        return path

    def test_default_60_seconds_stitches_files_and_formats(self):
        arrays = []
        for i in range(7):
            arrays.append(h5(self.inputs / f'{i}.h5', start=EPOCH + i * 10, base=i * 1000))
        self.run_cli('--format', 'both', '--channels', '0-4,4,50000-78000')
        y = segy(next(self.out.glob('*.sgy')))
        d = segd(next(self.out.glob('*.segd')))
        self.assertEqual([t['n'] for t in y], [6000] * 3 + [1000] * 3)
        self.assertEqual([r['n'] for r in d], [6000, 1000])
        expected = np.concatenate(arrays)
        for channel in range(3):
            np.testing.assert_array_equal(y[channel]['data'], expected[:6000, channel])
            np.testing.assert_array_equal(d[0]['traces'][channel]['data'], expected[:6000, channel])
        self.assertEqual(y[0]['time'], EPOCH * 1000000)
        self.assertEqual(d[0]['time'], (EPOCH - 315964800 + 18) * 1000000)
        self.assertAlmostEqual(d[0]['traces'][0]['latitude'], 68.1)
        self.assertAlmostEqual(d[0]['traces'][0]['longitude'], 14.2)
        self.assertEqual(struct.unpack_from('>i', y[0]['header'], 80)[0], round(14.2 * 3600000))
        self.assertFalse(list(self.out.glob('*.partial')))

    def test_configurable_length_and_dry_run(self):
        h5(self.inputs / 'a.h5', samples=2500)
        result = self.run_cli('--dry-run', '--trace-length', '5')
        self.assertFalse(self.out.exists())
        preflight = next(e for e in map(json.loads, result.stdout.splitlines()) if e['event'] == 'preflight')
        self.assertEqual(preflight['files'][0]['records'], 5)
        self.run_cli('--trace-length', '5')
        self.assertEqual(len(segy(next(self.out.glob('*.sgy')))), 15)

    def test_native_channels_not_columns(self):
        h5(self.inputs / 'a.h5')
        self.run_cli('--channels', '1-130,50000-78000')
        self.assertEqual([t['channel'] for t in segy(next(self.out.glob('*.sgy')))], [4, 50000])

    def test_reverse_column_order(self):
        values = h5(self.inputs / 'a.h5', channels=(50000, 4, 0))
        self.run_cli()
        traces = segy(next(self.out.glob('*.sgy')))
        np.testing.assert_array_equal(traces[0]['data'], values[:, 2])

    def test_round_duration_at_real_sample_interval(self):
        h5(self.inputs / 'a.h5', samples=30000, dt=.00204)
        result = self.run_cli()
        self.assertIn('60.000480', result.stdout)
        self.assertEqual(segy(next(self.out.glob('*.sgy')))[0]['n'], 29412)

    def test_midnight_and_gaps(self):
        midnight = int(datetime(2026, 6, 17, tzinfo=timezone.utc).timestamp())
        h5(self.inputs / 'a.h5', start=midnight - 5, samples=1000)
        h5(self.inputs / 'b.h5', start=midnight + 10, samples=1000)
        self.run_cli()
        files = sorted(self.out.glob('*.sgy'))
        self.assertEqual(len(files), 2)
        self.assertEqual(segy(files[0])[0]['n'], 500)
        traces = segy(files[1])
        self.assertEqual([t['n'] for t in traces], [500] * 3 + [1000] * 3)
        self.assertEqual(traces[3]['time'], (midnight + 10) * 1000000)

    def test_shots_fractional_time_stitch_skip_and_pack(self):
        a = h5(self.inputs / 'a.h5')
        b = h5(self.inputs / 'b.h5', start=EPOCH + 10, base=1000)
        nav = self.navigation(['2026:06:16:00:00:09.5', '2026:167:00:00:30.0'])
        self.run_cli('--mode', 'shot', '--p111', str(nav), '--p111-crs', 'wgs84', '--duration', '2', '--format', 'both')
        traces = segy(self.out / 'shots.sgy')
        self.assertEqual(len(traces), 3)
        np.testing.assert_array_equal(traces[0]['data'], np.concatenate([a[950:, 0], b[:150, 0]]))
        self.assertEqual(traces[0]['time'], EPOCH * 1000000 + 9500000)
        self.assertEqual(struct.unpack_from('>i', traces[0]['header'], 16)[0], 200)
        report = json.loads((self.out / 'shots.sgy.json').read_text())
        self.assertEqual(len(report['skipped_shots']), 1)
        self.assertEqual(len(segd(self.out / 'shots.segd')), 1)

    def test_missing_samples_exclude_whole_file(self):
        h5(self.inputs / 'a.h5', missing=(15,))
        h5(self.inputs / 'b.h5', start=EPOCH + 10)
        result = self.run_cli()
        self.assertIn('excluded entire file', result.stdout)
        self.assertEqual(segy(next(self.out.glob('*.sgy')))[0]['time'], (EPOCH + 10) * 1000000)

    def test_missing_csv_coordinate_fails(self):
        h5(self.inputs / 'a.h5', channels=(8,))
        result = self.run_cli(ok=False)
        self.assertIn('No exact receiver', result.stdout)
        self.assertFalse(self.out.exists())

    def test_duplicate_receiver_fails(self):
        h5(self.inputs / 'a.h5')
        with self.csv.open('a') as f:
            f.write('1,4,68,14,4,5\n')
        self.assertIn('Duplicate', self.run_cli(ok=False).stdout)

    def test_overlap_fails(self):
        h5(self.inputs / 'a.h5')
        h5(self.inputs / 'b.h5', start=EPOCH + 5)
        self.assertIn('Overlapping', self.run_cli(ok=False).stdout)

    def test_limit_failure_no_output(self):
        h5(self.inputs / 'a.h5', dt=.0005)
        self.assertIn('SEG-Y rev 1 limit', self.run_cli(ok=False).stdout)
        self.assertFalse(self.out.exists())
        self.run_cli('--trace-length', '1')

    def test_nonfinite_cleanup(self):
        h5(self.inputs / 'a.h5', scale=1e300)
        self.assertIn('overflowing', self.run_cli(ok=False).stdout)
        self.assertEqual(list(self.out.iterdir()), [])

    def test_output_collision(self):
        h5(self.inputs / 'a.h5')
        self.run_cli()
        path = next(self.out.glob('*.sgy'))
        before = path.read_bytes()
        self.assertIn('exists', self.run_cli(ok=False).stdout)
        self.assertEqual(before, path.read_bytes())

    def test_input_bounds(self):
        h5(self.inputs / 'a.h5')
        self.run_cli('--start', '2026-06-16T00:00:01.005Z', '--end', '2026-06-16T00:00:02Z')
        trace = segy(next(self.out.glob('*.sgy')))[0]
        self.assertEqual(trace['n'], 99)
        self.assertEqual(trace['time'], EPOCH * 1000000 + 1010000)

    def test_unsynchronized_shot_rejected(self):
        h5(self.inputs / 'a.h5', sync=0)
        nav = self.navigation(['2026:06:16:00:00:01'])
        result = self.run_cli('--mode', 'shot', '--p111', str(nav), '--p111-crs', 'wgs84', '--duration', '1', ok=False)
        self.assertIn('unsynchronized', result.stdout)

    def test_invalid_ranges_and_duration(self):
        h5(self.inputs / 'a.h5')
        for arg in [(' --channels', '5-1'), ('--trace-length', '0'), ('--trace-length', 'NaN')]:
            self.run_cli(arg[0].strip(), arg[1], ok=False)

    def test_cancellation_cleans_partial_files(self):
        channels = list(range(512))
        self.csv.write_text('lid,channel,latitude,longitude\n' + ''.join(f'1,{i},68,14\n' for i in channels))
        h5(self.inputs / 'a.h5', channels=channels, samples=60000, dt=.001)
        process = subprocess.Popen(self.command('--trace-length', '1'), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            for line in process.stdout:
                if '"event":"progress"' in line:
                    process.send_signal(signal.SIGTERM)
                    break
            stdout, stderr = process.communicate(timeout=20)
            self.assertEqual(process.returncode, 130, stdout + stderr)
            self.assertEqual(list(self.out.iterdir()), [])
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()


if __name__ == '__main__':
    unittest.main()
