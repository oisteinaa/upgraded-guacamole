# Cable Observatory

A unified local investigation app replaces `map_plot.py` and the old multi-page
Dash launcher. React/TypeScript + MapLibre render the map; a Python FastAPI service
provides bounded PostgreSQL and HDF5 access. Plotly is loaded when signal charts
are needed. Nord colors and locally bundled IBM Plex fonts follow house-report.

## Start the prepared local environment

From the repository root:

```bash
./scripts/run_map_local.sh
```

Open <http://127.0.0.1:8051>. The launcher starts the isolated PostgreSQL cluster
if needed, then serves the built frontend and API on loopback. It explicitly
selects `sensnetdb_local`, the project-local Unix socket on port 55432, and
`.local/recordings`. Stop the application with Ctrl+C. Stop PostgreSQL separately:

```bash
.local/runtime/pg/usr/lib/postgresql/15/bin/pg_ctl -D .local/pgdata stop
```

The source database snapshot is `.local/sensnetdb.dump`. `sensnetdb_local` contains
the restored source schema and data plus migration 004. A separate
`sensnetdb_test` clone is used for mutation tests. Production has not been migrated
or modified. `.local`, the virtual environment, copied recordings and frontend
build output are ignored by Git.

Three complete files, `000009.hdf5`, `000019.hdf5`, and `000029.hdf5`, were copied
from `/home/inst/DataCopy` on `10.147.20.10`. Each contains 4,902 samples × 25,236
channels (about 248 MB). Their headers suggest June 16, 2026; historical database
events cover April–June 2025. They are independent archive examples, not evidence
for those historical events. Neither time interpretation nor historical geographic
alignment has been marked verified.

## Investigation workflow

- Filter the event queue by stored date, class, route, review status, comment or ID.
  The Through date is inclusive. Pagination loads 50 rows; unlocated events remain
  visible under All routes. NULL class means Unclassified, never Normal Operations.
- Select an event to inspect metadata and save a classification with a reviewer
  name and evidence note. Updating the accepted class and inserting review history
  happen in one transaction. Stale edits return a conflict; reload before retrying.
  Reviewer names are self-reported in this local single-user installation.
- Search for a mast by route and name, e.g. `R06 M12`. Click a mast or inferred span
  for coordinates, matching distance and provenance. The water layer includes
  map candidates, which are not confirmed water crossings or submerged cables.
- Event windows require explicit verified references. When unavailable, open the
  independent recording browser. Choose an explicit header channel ID and window.
  Inspect waveform, RMS, variance, channel/time heatmap, and Welch spectrum.
  Drag to zoom the waveform/trends/heatmap to fetch a finer window; reset restores
  the first ten seconds. Playback moves a shared time cursor through these views.
- Weather is shown at the event's stored wall-clock time for the selected station.
  It is collected YR forecast context, not verified local measurement. No future
  weather rows are used. Missing/stale data and absent humidity are explicit.

## Signal semantics and performance

Signal review uses stored values multiplied by `header/dataScale` and the declared
unit. It does not silently apply the old pipeline's reversal, spatial unwrapping,
integration or sensitivity conversion. Explicit header IDs locate data columns;
no `channel / 4` or DataFrame row-index mapping is used.

Each request is capped at 600 seconds, two million samples for one waveform,
4,000 waveform display points, 16 heatmap channels and 400 time bins. Actual
min/max samples are retained in temporal order for waveform display. Heatmap and
heatmap buckets use raw-signal RMS for display. RMS/variance trends instead use fixed
ten-second frames, independent of plot zoom. Welch PSD uses the original selected window with
linear detrending, not the display envelope. A request reads only the requested
HDF5 slice and small heatmap blocks. Time/channel gaps are never reconstructed.
Files declaring missing samples or changed since indexing are rejected. A window
is clipped to the selected file; adjacent files are selectable independently.
Cross-file stitching and automatic weather/DAS alignment are deliberately absent
until timing/configuration continuity is verified.

### Along-fibre layers

The map uses `masteliste` channel coordinates, including the subsea route. Inferred
mast spans are an optional reference overlay, off by default. Choose:

- **AC RMS** (default): RMS after removing the window mean.
- **Band RMS**: integrated Welch power in a selectable band, initially 1–10 Hz.
  This is an exploratory band, not a validated event classifier.
- **Absolute peak**: maximum absolute mean-removed sample.
- **Variance** (advanced): population variance, in squared signal units.

All four metrics use the original scaled samples over fixed ten-second frames;
map zoom never changes their calculation. Partial final frames are identified.
The API caches metrics by file identity, frame, band and processing version under
`.local/metric-cache` (`DAS_METRIC_CACHE` can override this). Changed indexed files
are rejected. The initial upper color limit is the frame's 99th percentile;
limits remain locked across playback and recording changes until explicitly
rescaled, edited, or the metric/instrument/band changes. Linear and logarithmic
scales are available. Colors indicate amplitude, not classification or severity.

Display reduction keeps actual minimum/maximum channels in contiguous screen
buckets, preserving local peaks without connecting excluded fibre loops. Zooming
in exposes individual channels. Click a colored channel to open its signal;
recording/frame selection and playback update both map and signal review.
`GET /api/fibre?lid=1` provides reference geometry; recording metrics come from
`GET /api/recordings/{id}/metrics?lid=1&frame=0&metric=ac_rms&low=1&high=10`.

The supplied files resolve 17,010 channels exactly and 8,224 through short, bounded
coordinate interpolation on the same native channel axis. Two outer channels
remain outside the mapping bounds. The UI reports this explicitly; signal values
and channel IDs are never shifted. See [channel-mapping.md](channel-mapping.md)
for the evidence and interpolation rules. This does not verify historical events.

Map geometry is retained across updates. Event markers are clustered and capped
at the latest 5,000 matching located events; the queue exposes all results.
The basemap uses [OpenFreeMap](https://openfreemap.org/quick_start/) vector tiles
with a local Nord style and attribution, and requires internet; asset geometry, fonts, charts and application data are served locally.

## Build / install on another local machine

Use Python 3.11+, PostgreSQL 15+, and Node 22+:

```bash
python3 -m venv .venv-map
.venv-map/bin/pip install -r requirements-map.txt
cd web
npm ci
npm run build
cd ..
```

On this prepared machine Node is also available at
`.local/runtime/node-v22.16.0-linux-x64/bin`; add it to PATH for builds.
The isolated PostgreSQL binaries were extracted from the Debian server package
under `.local/runtime/pg`, without installing a system service. To reproduce:

```bash
mkdir -p .local/runtime .local/pgsocket
cd .local/runtime
apt-get download postgresql-15
dpkg-deb -x postgresql-15_*.deb pg
cd ../..
.local/runtime/pg/usr/lib/postgresql/15/bin/initdb \
  -D "$PWD/.local/pgdata" -L "$PWD/.local/runtime/pg/usr/share/postgresql/15" \
  --auth-local=trust --auth-host=scram-sha-256 --no-locale -E UTF8
.local/runtime/pg/usr/lib/postgresql/15/bin/pg_ctl -D .local/pgdata \
  -l .local/postgres.log -o "-k $PWD/.local/pgsocket -p 55432 -c listen_addresses=''" start
./scripts/clone_map_database.sh
.venv-map/bin/python scripts/index_recordings.py
```

`clone_map_database.sh` takes a read-only logical snapshot over SSH and refuses to
replace an existing database. Migration 004 is additive and rerunnable. It creates
`das_recordings`, `event_context`, `event_reviews` and time/filter indexes while
preserving existing event IDs, class IDs, rows and legacy insert statements. Do not
rerun the older once-only mast import migrations on the restored database.

## Capture and local replay

```bash
.venv-map/bin/python src/Capture/capture_zmq.py --replay --interval 10
```

This indexes recordings, prepares cached map metrics and publishes file-backed atomic snapshots;
multiple API workers see the same snapshot. Archive replay is always labeled
Replay, never Live. Without a verified instrument mapping, no live geographic
positions are guessed. With independently verified timing and channel mapping:

```bash
.venv-map/bin/python src/Capture/capture_zmq.py \
  --lid 1 --confirm-time --confirm-mapping --bind tcp://127.0.0.1:12345
```

The live notification transport accepts `{"dest_path":"/absolute/archive/file.hdf5"}`
for a completed file under `DAS_ARCHIVE_ROOT`. `pyzmq` is included for notification mode.
No whole raw array is serialized or posted to an in-memory HTTP global. The service
reads raw windows from the archive on demand. Acquisition time is separate from
publication time; stale status considers both. The supplied supervisor templates use ASGI, explicit environment variables and
`autostart=false`; configure and deliberately enable them before deployment.

Optional detection requires an explicit calibrated JSON rule file and a verified
legacy timestamp convention (`--rules rules.json --legacy-timezone Europe/Oslo`).
Example rule *shape*, not a validated threshold recommendation:

```json
[{"name":"Reviewed threshold configuration","lid":1,"channels":[0,4],
  "unit":"rad/(m*s)","processing":"stored values × dataScale","rms_limit":100}]
```

Thresholds in the old `event_limits` table refer to another processing pipeline
and are not reused. Candidate events get explicit recording/sample/channel
references and NULL class. A recording/channel is emitted once across retries;
this is a per-recording candidate, not an estimated incident duration. Route can
be supplied in a rule only after verification; it is not inferred from gid names.

## Configuration and deployment boundary

### Server alongside legacy

The server checkout is `/home/inst/oistein/upgraded-guacamole`. Legacy runs
from `/home/inst/upgraded-guacamole` on port 8050. Use the separate
`sensnet_observatory` service for the new app on port 8051; do not replace the
installed `sensnet_app`, capture or dataserver configurations.

Create `.venv-map` and install `requirements-map.txt` in the new checkout, then
build `web/dist` as above (or copy a build from the same source revision).
The server database requires `migrations/004_investigation.sql`; obtain approval
before applying this additive schema migration. The launcher checks for its
tables and reports missing prerequisites before opening the port.

Run `bash scripts/run_map_server.sh` for foreground operation. It serves on
`0.0.0.0:8051`, reads `sensnetdb` and `/home/inst/DataCopy`, and disables review
writes by default. Optional overrides go in `.local/map-server.env` using shell
assignment syntax. This launcher does not start capture, index recordings or
apply migrations. The recording browser stays empty until files are indexed.

The server deployment uses the independent systemd **user** service
`sensnet-observatory.service`, with linger enabled for `inst` so it starts at
boot and survives logout. Migration 004 was applied on 2026-09-16; the overview
API and both dashboard ports returned successfully. Manage it as `inst`:

```bash
systemctl --user status sensnet-observatory
systemctl --user restart sensnet-observatory
journalctl --user -u sensnet-observatory -n 100
```

The unit source is `deploy/sensnet-observatory.service`, installed at
`~/.config/systemd/user/sensnet-observatory.service`.

Alternatively, use Supervisor instead of the user service (stop and disable the
user service first to avoid a port collision). Install **only** the new configuration:

```bash
sudo cp supervisord/conf.d/sensnet_observatory.conf /etc/supervisor/conf.d/
sudo supervisorctl reread
sudo supervisorctl update sensnet_observatory
sudo supervisorctl status sensnet_observatory
```

Open `http://10.147.20.10:8051`. Logs are written to
`/home/inst/LOGS/sensnet_observatory.log`. Stop just the new app with
`sudo supervisorctl stop sensnet_observatory`. Do not restart all Supervisor
services. Authentication is not supplied; review writes remain disabled for
this shared-server configuration.

- `DAS_DATABASE_URL`: PostgreSQL DSN; defaults only to the local copy.
- `DAS_ARCHIVE_ROOT`: trusted root for indexed HDF5 paths.
- `DAS_LIVE_SNAPSHOT`: shared atomic capture snapshot path.
- `DAS_ENVIRONMENT`: visible environment label.
- `DAS_REVIEW_WRITES=0`: disable review writes.

Launch `python -m uvicorn src.Mapui.api:app --host 127.0.0.1 --port 8051` or run
`src/Mapui/map_plot.py` directly. `flask_app.py` and `Capture/restserver.py` now
expose the same ASGI app; old Dash callback/REST contracts are retired. Local
access uses loopback, same-origin browser writes and self-reported reviewer names.
Before multi-user deployment, connect authenticated identities to review records,
configure a restricted database role, and review the additive migration on the
server. No production rollout is included in the local test run.

## Checks

```bash
createdb -h "$PWD/.local/pgsocket" -p 55432 --template=sensnetdb_local sensnetdb_test
DAS_TEST_DATABASE_URL="dbname=sensnetdb_test host=$PWD/.local/pgsocket port=55432" \
  .venv-map/bin/python -m pytest tests/test_map_app.py -q
PLAYWRIGHT_BROWSERS_PATH=.local/browsers .venv-map/bin/python -m playwright install chromium
PLAYWRIGHT_BROWSERS_PATH=.local/browsers .venv-map/bin/python scripts/check_map_browser.py
```

Browser screenshots and local verification evidence are under `.local/`.

Browser review persistence can also be tested on an isolated second instance:

```bash
DAS_DATABASE_URL="dbname=sensnetdb_test host=$PWD/.local/pgsocket port=55432" \
  .venv-map/bin/python -m uvicorn src.Mapui.api:app --host 127.0.0.1 --port 8052
# In another terminal:
DAS_DATABASE_URL="dbname=sensnetdb_test host=$PWD/.local/pgsocket port=55432" \
  PLAYWRIGHT_BROWSERS_PATH=.local/browsers .venv-map/bin/python scripts/check_map_review.py
```

The test creates and removes a synthetic event only in `sensnetdb_test`. The
prepared local review database retains all 115,847 original unclassified events.
Validation on 2026-09-16: 58 Python tests passed, production frontend built, desktop/mobile
browser checks passed with no page errors, browser save/reload/history checks
passed, and three full recordings successfully published as archive replay.

Layer interaction checks (channel selection, zoom, scale controls, all layers and
playback across recordings):

```bash
npm test --prefix web
PLAYWRIGHT_BROWSERS_PATH=.local/browsers .venv-map/bin/python scripts/check_map_layers.py
```

### Signal channel ranges

In Recording browser, Number of channels sets the channel-ID width around Channel ID.
For example, channel 1000 and width 500 selects inclusive bounds 750–1250.
The Heatmap shows only recorded IDs inside those bounds; gaps and decimation can
reduce the actual count (dense inclusive bounds contain 501 IDs). AC RMS and variance
plot one value per selected channel against channel ID for the fixed 10-second
analysis frame at the playback cursor. AC RMS is the square root of per-channel
population variance (mean removed). Playback advances the displayed analysis frame;
time zoom does not change these fixed-frame statistics. Waveform and spectrum
show the recorded channel nearest the center.

Selecting a Mast span fills Channel ID with the midpoint of its endpoint IDs and
Number of channels with their difference, then loads that normal channel range
in the selected recording and plot. A half-integer midpoint preserves odd-width
ranges; endpoints sharing one channel use width 1. This is a channel-range preset,
not verification that the recording covers that geographic span. Spans remain
inferred connections, and endpoint bounds do not establish continuous monitored coverage.
Large reads are limited to 50 million values; shorten the time window or channel range
if the limit is exceeded.

### Event map visibility (deployed 2026-09-17)

The Signal layer sidebar includes Events controls: show/hide markers, latest
recorded day, last hour/24 hours/7 days, all dates or a custom Oslo wall-time
range; reviewed/unreviewed status; and independently selectable event classes.
The demonstration defaults to **Latest recorded day**, using the database's
latest event date. For live operation select **Last 24 hours**. Rolling ranges
refresh every minute and use server time. Custom end times are exclusive.
Filters apply before the map's 5,000-marker limit; zoomed-out clustering remains.

Map filters do not remove queue entries. The queue retains its own date/class/
review/search controls, while route selection applies to both views. Selecting
an event reveals its location in the separate selection overlay even outside
map filters or with markers hidden. Close selection to remove that override.
Settings currently reset to the demonstration default on page reload. Review
saving remains enabled in the server's `.local/map-server.env` for the demo.

### Cross-file signal windows (deployed 2026-09-17)

Both Event window and Recording browser now join consecutive indexed HDF5 files
for the requested interval. Archive windows support up to 600 seconds; event
context supports up to 120 seconds before and after the complete candidate.
The time axis remains relative to the selected anchor recording, so preceding
context can have negative seconds. Discovery event bounds include the complete
multi-file candidate rather than only its longest constituent file slice.

Joining requires matching sampling interval, scale, channel IDs/order, units,
instrument ID, processing and available acquisition configuration headers.
Boundary timestamp discrepancies up to one sample are treated as rounding.
Larger gaps/overlaps, configuration changes, changed files or missing-sample
metadata stop continuation. No interpolation or zero filling is performed.
The panel reports the number of files used and whether the requested window
was limited. Waveform, spectrum, heatmap and fixed analysis-frame statistics
use the joined sample sequence; display reduction does not feed the spectrum.
Existing sample/channel read budgets remain enforced.

### Recording playback (deployed 2026-09-17)

The signal-panel Play button advances through indexed recordings in acquisition
order, holding each loaded file for two seconds and waiting for signal and map
requests before proceeding. Starting from an event switches to its source
recording in archive mode. Playback retains the channel, stops at the archive
end or a signal-read error, and Pause retains the current recording. This is
file-by-file browsing, not real-time acquisition-speed replay; the timeline
slider remains available for inspecting a position within a file/window.

Map signal updates retain the previous data until the replacement arrives;
loading is indicated in the map footer. The previous fibre geometry likewise
remains visible while replacement geometry loads. A failed request keeps the
last successful layer and exposes the request error in Signal layer controls.

### Separate Live monitor workspace (deployed 2026-09-17)

Live monitor now has a dedicated full-width network map and capture-status
panel. It has no event queue, historical markers, event review, recording
selector, playback, or archive signal controls. Investigation requests and
playback stop when switching modes; investigation controls return on switching
back. Live polling is automatic, with no archive-replay fallback.

Only a fresh snapshot with API status `live` can supply the live signal layer.
Replay, offline, unverified-time, connection-error and stale states display
explicit status and remove the signal overlay, retaining static network assets
for orientation. Live AC RMS uses the published recording/frame, independently
of the investigation selection. The previous live frame may remain during a
replacement read, but only while its acquisition age is within 30 seconds.
At deployment the server `/api/live` reports offline: no capture published.


### Optional wind arrows

Enable **Wind arrows** in the map legend to show MET/YR wind forecasts at each
weather station. Live uses the latest forecast; Investigate uses the displayed
recording frame’s acquisition time. Arrows point in the direction the wind
blows (opposite the meteorological “from” bearing). Nonzero winds use an 18-pixel minimum for legibility, increasing linearly to
72 screen pixels at 30 m/s and remaining capped above 30 m/s. Colors are
green through 8 m/s, yellow above 8 through 18 m/s, and red above 18 m/s.
Calm or missing wind has only a station dot; hover for values and forecast time.
Forecasts older than two hours, or with unverified legacy times, have dashed station dots.
The overlay refreshes every minute while enabled and immediately when new signal
data loads. Historical queries exclude future valid/issue times and require a
weather value within the preceding two hours. Unverified recording times are
explicitly marked as provisional. Event filters do not change the weather time.
Drag the **Map legend** header to reposition the controls and wind key together;
positions are remembered separately for Live and Investigate. Keyboard users can
focus the header and use arrow keys to move it, or Home to reset its position. Speed and direction are paired by station, collection
time, forecast valid time and issue time via the read-only /api/map/wind endpoint.
