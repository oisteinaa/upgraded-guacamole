"""Read-only PostgreSQL fixtures; enable with DAS_TEST_DATABASE_URL."""
import os
from datetime import datetime, timezone

import pytest

from src.Mapui import api
from src.Mapui.db import rows

prefix="""WITH weather_stations(lid,name,latitude,longitude) AS (VALUES (1,'Test',68.,14.)),
weather_obs_types(type,abv) AS (VALUES (2,'wspd'),(3,'wdir')),
weather_obs(id,lid,type,value,source_time,forecast_updated_at,time) AS (
VALUES (1,1,2,5.,'2026-09-17 10:00+00'::timestamptz,'2026-09-17 09:00+00'::timestamptz,'2026-09-17 12:13'::timestamp),
(2,1,3,90.,'2026-09-17 10:00+00','2026-09-17 09:00+00','2026-09-17 12:13'),
(3,1,2,20.,'2026-09-17 11:00+00','2026-09-17 09:00+00','2026-09-17 13:13'),
(4,1,3,180.,'2026-09-17 11:00+00','2026-09-17 09:00+00','2026-09-17 13:13'),
(5,1,2,29.,'2026-09-17 10:00+00','2026-09-17 12:00+00','2026-09-17 14:13')) """

@pytest.mark.parametrize("hour,expected,direction", [(9,None,None),(10,5,90),(11,20,180),(15,None,None)])
def test_wind_time_matching(monkeypatch, hour, expected, direction):
    dsn = os.getenv("DAS_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Set DAS_TEST_DATABASE_URL for read-only SQL verification")
    monkeypatch.setenv("DAS_DATABASE_URL", dsn)
    monkeypatch.setattr(api, "rows", lambda sql, params: rows(prefix + sql, params))
    epoch = datetime(2026, 9, 17, hour, 30, tzinfo=timezone.utc).timestamp()
    station = api.map_wind(epoch)["stations"][0]
    assert station["speed"] == expected
    assert station["direction"] == direction
