import copy
from datetime import datetime, timezone
import unittest
from src.weather.weather_capture import current_values

class WeatherValuesTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 16, 12, 30, tzinfo=timezone.utc)
        self.payload = {'properties': {'meta': {'updated_at': '2026-09-16T11:00:00Z'}, 'timeseries': [
            {'time': '2026-09-16T12:00:00Z', 'data': {'instant': {'details': {
                'air_temperature': 8, 'wind_speed': 5, 'wind_from_direction': 270, 'relative_humidity': 86}}}},
            {'time': '2026-09-16T13:00:00Z', 'data': {'instant': {'details': {}}}}]}}

    def test_uses_current_not_future_and_includes_humidity(self):
        valid, updated, values = current_values(self.payload, self.now)
        self.assertEqual(valid.hour, 12)
        self.assertEqual(values['rhum'], 86)
        self.assertEqual(len(values), 4)

    def test_rejects_missing_invalid_and_nonfinite_humidity(self):
        for humidity in [None, -1, 101, float('nan')]:
            payload = copy.deepcopy(self.payload)
            details = payload['properties']['timeseries'][0]['data']['instant']['details']
            if humidity is None:
                del details['relative_humidity']
            else:
                details['relative_humidity'] = humidity
            with self.assertRaises((KeyError, ValueError)):
                current_values(payload, self.now)

    def test_rejects_stale_issue_and_time_step(self):
        for field in ['issue', 'step']:
            payload = copy.deepcopy(self.payload)
            if field == 'issue':
                payload['properties']['meta']['updated_at'] = '2026-09-15T00:00:00Z'
            else:
                payload['properties']['timeseries'][0]['time'] = '2026-09-16T09:00:00Z'
            with self.assertRaises(ValueError):
                current_values(payload, self.now)

    def test_rejects_future_only(self):
        self.payload['properties']['timeseries'].pop(0)
        with self.assertRaises(ValueError):
            current_values(self.payload, self.now)

if __name__ == '__main__':
    unittest.main()
