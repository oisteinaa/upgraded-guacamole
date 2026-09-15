# Offline DAS pattern discovery

This workflow reads bounded slices from an archive beside the data, groups
similar signals, and ranks unusual windows for human review. Clusters and
anomaly scores are **not event classes or probabilities**. No database or
source recording is modified. Use a separate output directory and run one
process per output directory.

## Install and run

Use Python 3.10+ and the dependencies in `requirements-ml.txt`. From the repo:

```bash
python3 -m venv .venv-ml
.venv-ml/bin/python -m pip install -r requirements-ml.txt
.venv-ml/bin/python -m src.Capture.event_discovery index /home/inst/DataCopy /home/inst/das-pilot
.venv-ml/bin/python -m src.Capture.event_discovery analyze /home/inst/das-pilot/index.json /home/inst/das-pilot
```

The module can also run directly as a standalone Python script on the client.
The defaults select 16 blocks of 32 adjacent recorded channels and up to 120
nonoverlapping 60-second windows. `--blocks`, `--channels-per-block`,
`--window-seconds`, `--max-windows`, and `--seed` control this budget.
The cap counts temporal windows, so the default maximum is 1,920 feature rows.
Selection uses seed 42 and does not load complete recordings into memory.
Indexing reads metadata across the archive; the metadata index grows with the
number of files. Analysis processes one window/block at a time.

The inspected DataCopy sample has 90 approximately ten-second files, 25,236
channels, a sample interval of 0.00204 seconds, and about 15 minutes of data.
It is a workflow pilot, not sufficient coverage to establish weather effects
or train validated event classifiers.

## Input checks and signal representation

Inputs must have `data` shaped `(samples, channels)` and the OptoDAS headers
used by the reader: `time`, `dt`, `dataScale`, `channels`, `unit`, `name`,
`gaugeLength`, `spatialUnwrRange`, `sensitivities`, and `missingSamples`.
Files declaring missing samples or another signal representation are skipped
with a reason. The reader supports phase rate per distance in `rad/(m*s)`.

Explicit header channel IDs define ordering. Channel blocks never cross gaps;
they have no assigned mast, span, route or geographic location. Mixed spatial
decimation in one configuration requires a mapping adapter. Different
acquisition configurations get separate models. No historical database mapping
or live reader reversal is assumed.

Features use stored values multiplied by `dataScale`, then linear detrending
per channel. No unwrapping, integration or conversion to displacement occurs.
Wrapping and optical/sensor artifacts can produce unusual spectra and require
review. The features are RMS, crest factor, kurtosis, dominant frequency,
spectral entropy, spatial RMS coefficient of variation, and normalized power
in 0.1–0.5, 0.5–1, 1–3, 3–10, 10–50, and 50–150 Hz bands. These bands are
exploratory, not rules identifying galloping or ice. Configurations below
300 samples/second are skipped because they cannot support all bands.

Compatible files can contribute to one window. Boundary discrepancies of up
to one sample are accepted as timestamp rounding and recorded in the summary.
Larger gaps/overlaps and configuration changes split sessions. There is no
interpolation. Windows use `floor(window_seconds / dt)` samples; incomplete
tails are recorded and omitted. Actual duration and every constituent sample
slice are exported.

## Optional weather context and sampling

Do not enable a join until acquisition timestamps have been independently
verified as Unix seconds and the weather writer's timezone convention is known.
The inspected headers plausibly indicate 16 June 2026, 00:00–00:15 UTC, but a
plausible date alone is not verification. Without confirmation the pilot can
still discover signal patterns and reports the time interpretation as unverified.

Import a CSV with columns `lid,time,variable,value`. Variables can be `temp`,
`wspd`, `wdir`, or their full names `temperature`, `wind_speed`,
`wind_direction`; explicitly named `humidity` is supported. Units are Celsius,
m/s, degrees, and percent. Never infer humidity from numeric type 4.

```bash
python3 -m src.Capture.event_discovery analyze /home/inst/das-pilot/index.json /home/inst/das-weather-pilot \
  --weather-csv weather.csv --weather-timezone Europe/Oslo --confirm-unix-time
```

Alternatively install `psycopg2-binary` in the isolated environment and pass
`--weather-dsn-env DAS_WEATHER_DSN`. Set that variable outside the script to
your PostgreSQL DSN. The connection starts a read-only transaction, queries a
bounded time range with the variable lookup, and rolls back. Secrets are not
written to output. The timezone argument is mandatory for database reads.

CSV timestamps with explicit offsets are preferred. Naive timestamps need
`--weather-timezone`; ambiguous/nonexistent DST times fail instead of being
guessed. A join uses the most recent value at or before the window start, with
a default maximum age of two hours (`--weather-max-age` in seconds). Source
times, ages, missing flags and stale flags remain visible. The database contains
collected YR forecasts, not necessarily measurements, and defaults to collection
time rather than forecast validity time. Humidity is absent in the current DB.

Both stations remain contextual until a station is explicitly selected with
`--station ID`. This enables balanced sampling across the cross-product of
temperature below/at-or-above 0°C and wind below 3, 3–8, above 8 m/s, plus an
unknown-weather group. Sampling redistributes unused capacity from empty groups.
Station selection is not a declaration that every block belongs to that station.
Weather is not used as a clustering or anomaly-model feature.

## Outputs, resume and review

- `index.json`: file paths, sizes, modification times, acquisition settings and
  channel IDs, plus rejected inputs. Re-index after source changes.
- `features.csv`: features with exact file/sample references, channel columns
  and IDs, session, weather context, cluster and anomaly score.
- `review.csv`: all windows ranked by anomaly score; `representative=true`
  marks the nearest example to each cluster center. Add `label` and set
  `label_verified=true` only after independent verification.
- `discovery-model.joblib`: per-configuration RobustScaler, K-means (up to six
  clusters) and Isolation Forest (200 trees), feature schema and preprocessing.
  Only load trusted joblib artifacts. Models with fewer than ten rows are
  omitted with an explicit status. This file is not an `event_ml` classifier.
- `summary.json`: settings, counts, cluster populations, timestamp status,
  boundary discrepancies, limitations and skipped-window reasons.
- `weather.json`: imported contextual weather records, including source times.
- `feature-cache.json`: resumable feature work, keyed by source file metadata,
  slices, acquisition configuration and preprocessing version. Identical reruns
  reuse features and deterministically refit models. Size/mtime checks are not
  content hashes; invalidate the cache if files were altered while preserving
  both. Do not edit a recording during analysis.

Rerunning preserves labels for unchanged review rows; labeled rows excluded
by the new selection are retained in `retired-review.csv`. Back up edited review
files before deliberately changing the archive or selection settings.

```bash
python3 -m src.Capture.event_discovery export-review /home/inst/das-pilot/review.csv labels.csv
```

Only verified labeled rows are exported. Multi-file windows become constituent
rows with the same session group. All labels must apply throughout the entire
reviewed window; subdivide mixed events before labeling. All rows from a file
must retain the same group. Related sessions/incidents must be consolidated
into a common group before supervised training. Unassigned station weather is
left blank in the training manifest.

**The existing supervised reader uses raw stored values**, while discovery
uses scaled, detrended values. The exported manifest is a source-slice and
label handoff, not a transfer of discovery features or model weights. Train a
new supervised model and predict using its own documented representation.
Constituent slices can have different durations, so standardize duration and
channel extent before training; the discovery export alone does not validate
training-set comparability. See [event-ml.md](event-ml.md).

Run tests with `python3 -m unittest discover -s tests`. A useful field evaluation
needs independent recording sessions, locations and weather conditions; a
successful pilot does not establish event accuracy or ice-loading sensitivity.
