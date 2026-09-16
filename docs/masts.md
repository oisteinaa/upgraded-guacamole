# Masts and spans

The server is `10.147.20.10`; database `sensnetdb`, schema `public`.
The four workbooks in `/mnt/c/Users/user/Downloads/masts` contain:

| Route | Masts | Inferred connections |
| --- | ---: | ---: |
| R06 Fygle–Solbjørn | 188 | 187 |
| R12 Svolvær–Kleppstad | 94 | 93 |
| R13 Kvitfossen–Svolvær | 101 | 100 |
| R14 Kleppstad–Fygle over Valberg | 196 | 195 |
| Total | 579 | 575 |

`masts` retains all 188 original R06 IDs and adds 391 masts. Original R06 CSV
coordinates are replaced by workbook coordinates with millimetre precision;
differences are under 0.01 m. `imported_at` is preserved for those existing rows;
`mapped_at` records the refreshed mapping. A pre-import export is retained in
`results/masts/masts-before-import.csv`.

Mast identity is `(route, mast)`, e.g. `('R06', 'M1')`. Names repeat across routes.
Leading zeroes are normalized, but suffixes such as `M38A` are retained.
`object_number` preserves the source asset ID; `route_position` gives connection
order. Workbook name, sheet, row and SHA-256 record provenance. The physical route
is independent of DAS `lid` and channel `gid`; no group names were repurposed.

Coordinates are converted from inferred WGS84 / UTM zone 33N (EPSG:32633) to WGS84
latitude/longitude (EPSG:4326), consistent with the existing map code and channel
alignment. The workbooks themselves do not declare a CRS. Nearest channels are
selected by WGS84 ellipsoidal distance to **all** 25,235 stored channel positions,
including ungrouped channels, without spatial decimation. Ties resolve by `lid`,
then channel. `(channel, lid)` retains its foreign key to `masteliste`.

## Span connections and limits

`mast_spans` stores endpoint mast IDs, route, order, straight-line endpoint
distance, connection evidence, review notes, water status and installation.
All connections start as `connection_status = 'inferred'`. These are connections
between supplied mast locations, not a certified inventory of physical spans.
There are no invented cross-route connections, station endpoints or missing masts.

R06, R12 and R13 follow numeric mast order. R13 lacks M38, so M37–M39 is explicitly
flagged for review. R14 has missing numbers and lettered replacement masts; its
geography and mapped channel progression support descending channel order. In
particular, the sequence is M33A, M34A, M35A, M36A, M37A, M38A, M35, M36, M37,
M40. Numeric sorting would create backtracking spans. Unusual numbering is
flagged for review rather than silently presented as verified connectivity.

R06 M184–M188 match endpoint channel 101899 at approximately 17.5–498.5 m.
R14 M1 matches channel 28464 at about 30.1 m. Other masts are within 10 m of their
nearest channels. Spans touching distant matches have review notes.

`straight_length_m` is ellipsoidal endpoint distance at import, not sagged cable
length, underwater cable length or DAS fibre distance. Changing endpoint
coordinates requires recomputing length and channel mapping. The view's GeoJSON
is an illustrative straight line; it does not reconstruct submarine routes.
Channel numbers at span endpoints do not prove continuous monitored coverage.

## Water and cable placement

Water is a span attribute, not a mast attribute. `water_status` is one of:

- `unknown`: no confirmed classification; does not mean land.
- `map_candidate`: possible water crossing from map review.
- `confirmed_water`: independently confirmed water crossing.
- `confirmed_land`: independently confirmed absence of a water crossing.

Seven map candidates were visually screened against
[Kartverket Topografisk Norgeskart WMS](https://github.com/kartverket/tjenestedokumentasjon/blob/master/WMS/README.md)
on 2026-09-16. Source: © Kartverket. Endpoint lines were sampled against water fill
colours in WMS `topo` images, followed by visual review. This is an approximate,
non-exhaustive screen, not a shoreline intersection calculation; narrow water
features, cartographic symbols and raster resolution can produce omissions.
Unflagged connections remain `unknown`, not `confirmed_land`.

| Route | Mast pair | Approximate endpoint distance |
| --- | --- | ---: |
| R06 | M11–M12 | 281 m |
| R06 | M12–M13 | 190 m |
| R06 | M19–M20 | 237 m |
| R06 | M44–M45 | 2,233 m |
| R06 | M86–M87 | 1,920 m |
| R06 | M177–M178 | 213 m |
| R12 | M82–M83 | 319 m |

`installation` is separate: `unknown`, `overhead`, `submerged`, `underground`, or
`mixed`. It remains `unknown` for every connection until confirmed. The view's
nullable `crosses_water` boolean is true/false only for confirmed water/land;
map candidates and unknowns both yield NULL. Use `water_status` to find candidates.

## Queries

`v_mast_spans` joins span metadata to both mast endpoints, their channels,
coordinates and matching distances, with an EPSG:4326 `geometry_geojson`
LineString (longitude first). `v_water_spans` selects map candidates and confirmed
water crossings. No PostGIS extension is required.

```sql
SELECT route, mast, latitude, longitude, channel, channel_distance_m
FROM public.masts ORDER BY route, route_position;

SELECT route, from_mast, to_mast, from_channel, to_channel,
       straight_length_m, water_status, installation, geometry_geojson
FROM public.v_mast_spans ORDER BY route, span_order;

SELECT route, from_mast, to_mast, water_status, installation
FROM public.v_water_spans ORDER BY route, span_order;

SELECT route, from_mast, to_mast, review_reason
FROM public.v_mast_spans WHERE review_reason IS NOT NULL
ORDER BY route, span_order;
```

## Import and verification

`scripts/prepare_mast_import.py` uses Python 3 with openpyxl, numpy and pyproj.
It is an offline, deliberately dataset-specific generator for the four supplied
workbooks. It checks expected counts, identifiers, coordinate bounds and R06
identity before producing a single transactional migration and audit CSVs.
The seven reviewed candidate pairs are explicitly recorded in the generator.
Do not treat this as a generic automatic importer for different source files.

The snapshot JSON has `masts` (all original columns) and `channels` (`id`, `lid`,
`channel`, `latitude`, `longitude`, `gid`) arrays, exported with a read-only
database transaction. The generated migration verifies the original mast
snapshot and matched channel coordinates before writing; stale snapshots fail.

```bash
python3 scripts/prepare_mast_import.py \
  /mnt/c/Users/user/Downloads/masts /tmp/masts-server-snapshot.json

ssh inst@10.147.20.10 "psql -U sensnetdbu -h localhost -d sensnetdb -X -v ON_ERROR_STOP=1" \
  < migrations/003_mast_routes_spans.sql

ssh inst@10.147.20.10 "psql -U sensnetdbu -h localhost -d sensnetdb -X -v ON_ERROR_STOP=1" \
  < migrations/verify_mast_routes_spans.sql
```

The migration is once-only, not an upsert: reapplying it fails safely instead of
overwriting later classifications. Its first execution was tested with final
ROLLBACK before the committed application. Verification checks row counts,
legacy IDs, channel references, R14 order, the R13 gap, and unknown cable
placement. Constraint probes for cross-route endpoints, invalid water status and
duplicate mast names are rolled back without changing stored data.
