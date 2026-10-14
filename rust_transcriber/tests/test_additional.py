import csv
import json
import tempfile
import unittest
from pathlib import Path
import h5py
import numpy as np
from test_conversion import Conversion, h5, segy, segd, EPOCH


class Additional(Conversion):
    # Inherit fixture helpers only, not the parent tests (filtered below).
    def test_utm_source_conversion(self):
        h5(self.inputs / 'a.h5')
        nav = self.navigation(['2026:06:16:00:00:01.000001'])
        with nav.open() as f:
            lines = list(csv.reader(f))
        lines[1][12], lines[1][13] = '500000', '0'
        with nav.open('w') as f:
            csv.writer(f).writerows(lines)
        self.run_cli('--mode', 'shot', '--p111', str(nav), '--p111-crs', 'utm33n', '--duration', '1')
        report = json.loads((self.out / 'shots.sgy.json').read_text())
        shot = report['output']['blocks'][0]['shot']
        self.assertAlmostEqual(shot['longitude'], 15.)
        self.assertAlmostEqual(shot['latitude'], 0.)
        self.assertEqual(report['output']['blocks'][0]['start'], (EPOCH + 1) * 1000000 + 10000)

    def test_acquisition_configuration_boundary(self):
        for i in range(2):
            path = self.inputs / f'{i}.h5'
            h5(path, start=EPOCH + i * 10)
            with h5py.File(path, 'a') as f:
                f['header/gaugeLength'] = 8. if i == 0 else 16.
        self.run_cli()
        self.assertEqual(len(segy(next(self.out.glob('*.sgy')))), 6)

    def test_full_channel_grid_change_splits_selected_subset(self):
        h5(self.inputs / 'a.h5', channels=(0, 4))
        h5(self.inputs / 'b.h5', channels=(0, 8), start=EPOCH + 10)
        self.run_cli('--channels', '0')
        self.assertEqual(len(segy(next(self.out.glob('*.sgy')))), 2)

    def test_roi_change_splits_selected_subset(self):
        for i in range(2):
            path = self.inputs / f'{i}.h5'
            h5(path, start=EPOCH + i * 10)
            with h5py.File(path, 'a') as f:
                f['demodSpec/roiDec'] = np.array([4 if i == 0 else 8], dtype='u4')
        self.run_cli('--channels', '0')
        self.assertEqual(len(segy(next(self.out.glob('*.sgy')))), 2)

    def test_float_samples_and_variable_string(self):
        path = self.inputs / 'a.h5'
        h5(path)
        with h5py.File(path, 'a') as f:
            del f['header/unit']
            f['header/unit'] = 'rad/(m*s)'
            del f['data']
            f['data'] = np.full((1000, 3), 1.5)
        self.run_cli()
        self.assertEqual(segy(next(self.out.glob('*.sgy')))[0]['data'][0], .375)

    def test_multiple_shots_one_file(self):
        h5(self.inputs / 'a.h5')
        nav = self.navigation(['2026:06:16:00:00:01', '2026:06:16:00:00:03'])
        self.run_cli('--mode', 'shot', '--p111', str(nav), '--p111-crs', 'wgs84', '--duration', '1', '--offset', '-0.5', '--format', 'both')
        self.assertEqual(len(list(self.out.glob('*.sgy'))), 1)
        self.assertEqual(len(segy(self.out / 'shots.sgy')), 6)
        self.assertEqual(len(segd(self.out / 'shots.segd')), 2)

    def test_independent_segy_reader(self):
        import segyio
        h5(self.inputs / 'a.h5')
        self.run_cli()
        with segyio.open(str(next(self.out.glob('*.sgy'))), ignore_geometry=True) as f:
            self.assertEqual(f.tracecount, 3)
            self.assertEqual(len(f.trace[0]), 1000)
            self.assertEqual(f.trace[0][1], .25)


# Do not repeat the conversion suite inherited for its temporary-directory helpers.
def load_tests(loader, tests, pattern):
    names = [name for name in Additional.__dict__ if name.startswith('test_')]
    return unittest.TestSuite(Additional(name) for name in names)
