"""Integration check using synthetic recordings; does not establish field accuracy."""
import csv
import tempfile
import unittest
from pathlib import Path

import numpy as np

try:
    import h5py
    import joblib
    import sklearn
except ImportError:
    h5py = None

from src.Capture.event_ml import CLASSES, train, classify_window


@unittest.skipIf(h5py is None, 'Install requirements-ml.txt for integration checks')
class TrainingTest(unittest.TestCase):
    def test_train_and_predict(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / 'labels.csv'
            with manifest.open('w', newline='') as stream:
                writer = csv.writer(stream)
                writer.writerow(['path', 'start_sample', 'stop_sample', 'channel_start',
                                 'channel_stop', 'sample_rate_hz', 'label', 'group'])
                for group in range(6):
                    for index, label in enumerate(CLASSES):
                        filename = f'{group}-{index}.hdf5'
                        signal = (index + 1) * np.sin(2 * np.pi * (index + 1) * np.arange(200) / 20)
                        with h5py.File(root / filename, 'w') as recording:
                            recording['data'] = signal[:, None]
                        writer.writerow([filename, 0, 200, 0, 1, 20, label, str(group)])
            model_path = root / 'model.joblib'
            report = train(manifest, model_path)
            self.assertEqual(report['samples'], 24)
            self.assertEqual(np.asarray(report['confusion_matrix']).sum(), 24)
            for fold in report['folds']:
                self.assertFalse(set(fold['train_groups']) & set(fold['test_groups']))
            self.assertTrue(Path(str(model_path) + '.metrics.json').exists())
            result = classify_window(joblib.load(model_path), signal[:, None], 20)
            self.assertAlmostEqual(sum(result['probabilities'].values()), 1)


if __name__ == '__main__':
    unittest.main()
