# Distributed weather capture

Migration `005_distributed_weather.sql` and the updated collector were applied to
server `10.147.20.10` / `sensnetdb` and local `sensnetdb_local` on 2026-09-16.
Both received successful initial captures: 17 points × 4 variables = 68 rows.
Server cron continues at minute 13 of every hour using the same collector path.
The local collector runs on demand with `./scripts/capture_weather_local.sh`
while the local PostgreSQL instance is running. No local scheduler is installed.

The existing Kråkern Bru and Leknes locations remain unchanged. Fifteen new
points use exact mast coordinates from `results/masts/masts.csv`:

| Route | Mast forecast points |
| --- | --- |
| R06 Fygle–Solbjørn | M44, M67, M95, M137, M177 |
| R12 Svolvær–Kleppstad | M1, M38, M72 |
| R13 Kvitfossen–Svolvær | M1, M39 |
| R14 Kleppstad–Fygle | M1, M43, M83, M123, M160 |

Selection traversed the imported route positions and added a point when it was
at least approximately 5 km from all already selected points, including the two
original locations (local approximation: 111.2 km/latitude degree and
41.4 km/longitude degree). This samples geographic differences along the route,
including coastal and inland sections, without querying every mast. It is an
initial spatial sampling design, not a demonstrated set of distinct microclimates
or an optimized terrain/exposure study. Weather contrasts must be measured over
time. No reliance on inconsistent channel gid names is made. Route/mast identity
and selection notes are stored on `weather_stations`; lids are database-assigned.

[MET Locationforecast](https://api.met.no/doc/locationforecast/datamodel) supplies
model forecasts, not station measurements. Its Nordic grid is approximately
2.5 km; individual span exposure, icing and gusts may differ substantially.
Humidity is `relative_humidity` at 2 m, stored as `rhum`, percent. The migration
allocates its type ID rather than assuming type 4 is available (both current
installations assigned 4). Temperature, wind speed and direction retain their
existing IDs. New locations have NULL altitude because the workbook does not
supply verified ground elevations; MET uses its terrain model. Existing known
station elevations are sent. Request coordinates are rounded to four decimals.

`weather_obs.time` retains Oslo local collection time for existing consumers.
New rows also store timezone-aware `source_time` (forecast valid time),
`forecast_updated_at` (model issue time), and `collected_at` (retrieval time).
Historical rows remain untouched with NULL provenance. Use the explicit timestamps
for future alignment, and never treat collection time as the forecast valid time.
Backtests should also ensure the forecast was available before the decision time.
The collector chooses the latest time step no later than retrieval, rejects steps
older than two hours and forecasts issued more than twelve hours ago, validates
finite values and humidity bounds, and fails clearly on missing variables.

An API response cache honors Expires. Each station commits atomically; a station
failure does not lose others, but yields a nonzero run exit status. A partial
unique index on `(lid,type,source_time,forecast_updated_at)` prevents duplicate
rows when repeating the same forecast capture. A newer issue for the same valid
time is retained. Migration is repeatable and preserves legacy observations.

The server's previous collector is backed up as
`src/weather/weather_capture.py.before-weather-20260916`. The collector uses
`WEATHER_DATABASE_URL`, then `DAS_DATABASE_URL`, otherwise the existing server
connection settings. Cache defaults to `~/.cache/sensnet-weather`; override with
`WEATHER_CACHE_DIR` or `--cache-dir`. Only psycopg2 is required beyond the Python
3.9+ standard library; the former yr_weather dependency is no longer needed.

Validation: ` .venv-map/bin/python -m unittest tests.test_weather_capture`.
