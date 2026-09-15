import unittest
import numpy as np
from src.Capture.event_ml import CLASSES, FEATURES, extract_features, classify_window


class FeaturesTest(unittest.TestCase):
    def test_frequency_and_amplitude(self):
        signal = 2 * np.sin(2 * np.pi * 2 * np.arange(1000) / 100)
        f = extract_features(signal[:, None], 100)
        self.assertAlmostEqual(f['dominant_hz'], 2)
        self.assertAlmostEqual(f['ac_rms'], np.sqrt(2))
        self.assertGreater(f['low_power_fraction'], .99)

    def test_constant_and_missing_weather(self):
        f = extract_features(np.ones((100, 2)), 10)
        self.assertTrue(np.isfinite(list(f.values())).all())
        self.assertEqual(f['ac_rms'], 0)
        self.assertEqual(f['humidity_missing'], 1)
        self.assertEqual(extract_features(np.ones((100, 2)), 10,
                                         {'humidity': 0})['humidity_missing'], 0)

    def test_bad_inputs(self):
        for signal, rate in [(np.zeros((7, 1)), 10), (np.zeros((10, 1)), 0),
                             (np.full((10, 1), np.nan), 10)]:
            with self.assertRaises(ValueError):
                extract_features(signal, rate)

    def test_probability_order_and_review(self):
        class Model:
            classes_ = list(reversed(CLASSES))
            def predict_proba(self, x):
                return [[.4, .3, .2, .1]]
        result = classify_window({'version': 1, 'features': FEATURES,
                                  'classes': CLASSES, 'model': Model()},
                                 np.zeros((100, 1)), 10)
        self.assertEqual(result['predicted_class'], 'External Interference')
        self.assertTrue(result['needs_review'])
        self.assertEqual(result['window_duration_s'], 10)
        self.assertEqual(result['probabilities']['Normal Operations'], .1)


if __name__ == '__main__':
    unittest.main()
