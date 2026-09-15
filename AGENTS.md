# Project instruction

This project is taking data from DAS interrogator using h5py file formats
Aim is a dash board with event detection for galloping cable, ice build up, vegatation strike or other irregularities
It takes in data from YR like temperature, wind speed, direction would like to add humidity

## Database context (inspected and class migration applied on 2026-09-16)

### Access

PostgreSQL is available through SSH. Use this working command (SQL runs on
 the remote host; no local PostgreSQL service is needed):

```bash
ssh inst@10.147.20.10 "psql -U sensnetdbu -h localhost -d sensnetdb -X -c '\dt'"
```

For inspection queries use `BEGIN READ ONLY; ...; COMMIT;`. Do not assume
permission to modify database data or schema from permission to read it.
All eight tables below are in `public`. The `events.classid` foreign key to
`event_classes.classid` is enforced; other relationships below are logical
conventions, not database-enforced references.
Snapshot counts and date coverage will change; re-query when freshness matters.

### Tables and keys

| Table | Columns | Keys / meaning |
| --- | --- | --- |
| `weather_obs` | `id bigint`, `time timestamp`, `lid integer`, `type integer`, `value double precision` | PK `id`; one weather variable per station/time/row |
| `weather_obs_types` | `type integer`, `time timestamp`, `abv varchar(4)`, `name varchar(32)`, `unit varchar(16)` | PK `type`; join `weather_obs.type = weather_obs_types.type` |
| `weather_stations` | `lid integer`, `time timestamp`, `name varchar(64)`, `latitude`, `longitude`, `altitude` (double precision) | PK `lid`; join `weather_obs.lid = weather_stations.lid` |
| `masteliste` | `id integer`, `time timestamp`, `channel integer`, `distance`, `latitude`, `longitude` (double precision), `lid`, `mid`, `gid`, `tid` (integer), `comment varchar(128)` | PK `id`; unique `(channel, lid)`; channel position and grouping metadata |
| `event_data_types` | `data_type integer`, `name varchar(16)`, `unit varchar(16)` | PK `data_type`; metric lookup |
| `event_limits` | `id integer`, `time timestamp`, `name varchar(25)`, `gid integer`, `data_type integer`, `limit double precision`, `absolute boolean` | PK `id`; threshold by group and metric; `absolute` defaults false |
| `event_classes` | `classid smallint`, `name varchar(32)` | PK `classid`; unique, non-null `name` |
| `events` | `id integer`, `time timestamp`, `type smallint`, `value double precision`, `comment varchar(80)`, `classid smallint` | PK `id`; `type` corresponds to `event_data_types.data_type`; nullable FK `classid` references `event_classes.classid` |

All `time` columns are **timestamp without time zone**, defaulting to
`CURRENT_TIMESTAMP`. The inspected database session timezone is `Europe/Oslo`.
Verify writer timezone conventions before aligning DAS and weather timestamps,
particularly across daylight-saving transitions. These defaults describe insert
 time, not necessarily source observation/acquisition time.
Primary-key indexes, the `(channel, lid)` unique index and the
`event_classes.name` unique index are present;
large time-range queries may scan tables.

### Weather

| type | abv | name | unit |
| --- | --- | --- | --- |
| 1 | temp | Air Temperature | Degrees C |
| 2 | wspd | Wind Speed | m/s |
| 3 | wdir | Wind direction | Degrees |

**Humidity is not currently defined or stored.** Adding it requires a lookup
entry and collector support; do not assume that type 4 already means humidity.

Stations:

| lid | name | latitude | longitude | altitude |
| --- | --- | --- | --- | --- |
| 1 | Kråkern Bru | 68.01885 | 14.18153 | 5 |
| 2 | Leknes | 68.14812 | 13.61147 | 8 |

At inspection, station 1 had 12,441 rows per variable and station 2 had 12,437.
Coverage starts 2025-04-14 and ends 2026-09-16 00:13:02.097193; this does not
establish uninterrupted coverage. `src/weather/weather_capture.py` fetches YR
Locationforecast `.now().details` per station and inserts the three variables
with database-default timestamps. Despite the table name, these are collected
forecast values, not necessarily direct weather-station measurements.
For ML, match station/location and time, check missing/stale values, and avoid
using future weather. Do not join `masteliste.lid` to weather-station `lid`
without verifying its meaning: all channel rows have lid 1 while two weather
stations cover different locations.

### DAS channel positions

`masteliste` represents the interrogator's maximum spatial sampling. The current
DAS data is spatially decimated by a factor of 4, which explains the
every-fourth-row selection in `get_mastliste()`. Missing channel ranges correspond
to fibre loops intentionally excluded from monitoring; they do not require
reconstruction or treatment as missing monitored coverage.

`masteliste` has 25,235 rows, all with lid 1 and non-null latitude/longitude.
All metadata timestamps are 2026-04-16 15:32:36.355238. `mid` and `tid` are null
throughout. Channel IDs span 0–101899 with gaps; the sampled initial sequence
is 0, 4, 8, 12, 16. Do not equate row index with DAS channel ID or assume dense
coverage. Distance units and route origin are not declared in the schema;
distance is not globally monotonic across the route.

| gid | rows | min channel | max channel |
| --- | --- | --- | --- |
| 1 | 3668 | 87231 | 101899 |
| 2 | 379 | 85715 | 87227 |
| 3 | 1441 | 79951 | 85711 |
| 4 | 1495 | 71371 | 77347 |
| 5 | 7118 | 0 | 28468 |
| 6 | 1793 | 28472 | 35640 |
| 7 | 3902 | 36144 | 51748 |
| 8 | 3780 | 52920 | 68036 |
| NULL | 1659 | 35644 | 79947 |

Ranges are bounds and may include excluded fibre loops. Preserve ungrouped
channels explicitly. Some stored comments have replacement characters.

**Mapping inconsistencies:** masteliste comments identify gid 1 with
Solbjørn/Flakstad, gid 5 with Fygle/Malnes and gid 8 with LAS/Osan/Kvitfossen;
the event-limit names below assign different routes to these same gids.
Resolve this discrepancy before using group names for locations or labels.
The channel metadata also postdates the stored events, so historical channel
mappings cannot be assumed to match the current table.

`src/sensnetlib/dbfunc.py:get_mastliste()` selects every fourth row by id to match
the current factor-of-four spatial decimation, filters `channel < 33421`, sorts channel descending,
and limits to 8356 rows. `capture_zmq.py` reverses the signal channel axis and
uses DataFrame indices to aggregate RMS by gid. Validate the file's channel
mapping, subsampling and ordering against explicit `(lid, channel)` keys before
using this helper for ML or geographic localization.

### Events and thresholds

`event_data_types`: 1 = `rms`, 2 = `variance`; both units are blank.
All eight current limits use type 1 and `absolute = false`:

| gid | event_limits.name | limit |
| --- | --- | --- |
| 1 | Osan-Kvitfossen | 2000 |
| 2 | Kleppstad-Tjeldbergvik | 2500 |
| 3 | Gimsøystraumen | 500 |
| 4 | Fygle-Malnes | 1000 |
| 5 | Skreda-Leknes Lufthavn | 1000 |
| 6 | Vareid-Napp | 1000 |
| 7 | Flakstadpollen | 1000 |
| 8 | Solbjørn-Flakstad | 1000 |

There are 115,847 events, spanning 2025-04-22 23:10:22.360459 through
2025-06-02 19:57:30.687395, all type 1 (RMS). Historical comments include Vareid
(59,416), Group 3 (19,569), Offersøy sør (10,483), Leknes 1 (7,997), Ramberg
(6,828), Fygle (5,049), Leknes (2,144), Offersøy nord (1,546), Group 2 (973),
Group 4 (931), Solbjørn (885), Group 7 (24), and Napp (2).
None of these comment values equals a current event-limit name.

`event_detector.py` currently stores the metric ID, threshold-crossing value,
and limit name as the event comment. `get_event_locations()` tries joining
`events.comment = event_limits.name`, then gid to mean masteliste coordinates;
this cannot resolve the inspected historical events. Events have no explicit
gid/channel, end time, duration, file reference or confidence. The optional
`classid` added on 2026-09-16 is NULL for all 115,847 existing events.
Capture code uses processing wall-clock time; verify original acquisition time
before correlating files to database records.

### Machine-learning implications

Target classes are `Normal Operations`, `Ice Loading`, `Wind Galloping`, and
`External Interference`. **The database event types are signal metrics, not
these classes.** Threshold alarms can identify candidate windows for review,
but are not ground-truth ice, galloping or interference labels; absence of an
alarm is not proof of normal operation. The class lookup exists, but legacy
events remain unclassified. Obtain verified labels and historical channel/time
alignment before training from these records. See `docs/event-ml.md` for the
offline pipeline and labeling manifest.


### Event class migration (applied 2026-09-16)

`migrations/001_event_classes.sql` creates and seeds `event_classes` and adds
nullable `events.classid` with foreign key `events_classid_fkey`.

| classid | name |
| --- | --- |
| 1 | Normal Operations |
| 2 | Ice Loading |
| 3 | Wind Galloping |
| 4 | External Interference |

IDs are one-based database identifiers, not zero-based indices into the Python
`CLASSES` list. Keep `events.type` for RMS/variance metric identity. NULL classid
means unclassified; it must not be interpreted as Normal Operations. No default
class and no historical backfill are applied. Existing inserts that specify
`type, value, comment` continue to work. To retain legacy rows when reading
class names, use `LEFT JOIN event_classes c ON c.classid = events.classid`.

Apply/reapply the migration with:

```bash
ssh inst@10.147.20.10 "psql -U sensnetdbu -h localhost -d sensnetdb -X -v ON_ERROR_STOP=1" < migrations/001_event_classes.sql
```

The migration is transactional and was successfully rerun. Verification via
`migrations/verify_event_classes.sql` confirmed a legacy insert gets NULL,
a valid class is accepted, and an invalid class fails foreign-key enforcement;
all test writes were rolled back without consuming sequence IDs. Existing
115,847 events remained unclassified.
