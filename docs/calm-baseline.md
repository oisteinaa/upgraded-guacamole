# Calm-weather activity reference

The map's **Signal layer**, **Live monitor**, and **Signal investigation** offer
**Activity display: Raw / Calm baseline**. A compatible reference selects Calm
baseline initially. An explicit choice persists while moving between recordings
within that view. Waveform and spectrum always retain physical units.

The calm score for a metric is `(value - median) / scale`, where
`scale = max(1.4826 * MAD, 0.05 * median)`. Median and median absolute deviation
are fitted independently for each recorded channel and acquisition configuration.
The relative floor prevents nearly constant references from producing arbitrarily
large scores; zero/nonfinite scales are unavailable. This is a robust departure
score, not a Gaussian probability, incident severity or event classification.

Colors run from 0 to 10. Negative departures use the lowest color, and scores above
10 saturate only the color. Tooltips retain the signed, unclipped score, raw metric
and calm median. The map tooltip also identifies a scale floor. Missing references
remain gaps. Explicitly selecting Calm baseline never substitutes raw values into
the score display. Raw controls retain their independent amplitude scale.

Normalized activity uses complete ten-second source-file frames, with the same
sample rounding and mean removal as map metrics. Zooming does not recompute a
reference or change a frame's score. Stitched investigation keeps each constituent
file's frame origin and excludes boundary slivers caused by timestamp rounding
within one sample. Incomplete final frames remain raw-only. Normalized heatmaps
therefore have different time resolution from the raw display heatmaps. Channel
scores are computed before display reduction; live bins retain maximum scores.
Signal investigation also offers peak and 1–10 Hz band RMS, and a selected-channel
time-trend checkbox in calm activity mode. Waveform and spectrum are unchanged.

## Train and activate explicitly

Use the same archive, database and metric cache as the dashboard. Connections are
read-only; this command does not index recordings, change database rows, create
events or alter capture settings. It writes baseline artifacts and metric caches.

```bash
.venv-map/bin/python -m src.Mapui.train_calm
# Inspect the timestamped JSON report before activating an operational reference.
.venv-map/bin/python -m src.Mapui.train_calm --activate
```

Configuration:

- `DAS_DATABASE_URL`, `DAS_ARCHIVE_ROOT`, and `DAS_METRIC_CACHE` use the normal
  dashboard conventions. Set them explicitly when training against the server.
- `DAS_CALM_BASELINES` defaults to `.local/calm-baselines`. It contains immutable
  timestamped JSON/NPZ artifacts and an atomically replaced `active.json` pointer
  manifest. No pickle or executable model serialization is used.
- `--start` and `--end` accept UTC epoch seconds; default search is the preceding
  30 days. `--wind-max` defaults to 3 m/s, `--temperature-min` to 2°C (strictly
  greater), and `--sample-minutes` to 1. Larger sampling intervals can leave too
  little calm evidence for qualification.
- `--activate` replaces the active manifest only after a completed fit with
  qualified channels. Without it, training writes a candidate report. To promote
  an already inspected candidate without refitting, copy its JSON to a temporary
  file inside the baseline directory and atomically rename it to `active.json`.
  Keep its referenced NPZ file beside it. The same operation restores an older
  reference. No service restart is required for scoring an activated reference;
  live snapshots refresh with the next acquisition and demo cache IDs change.

Only recordings marked verified for time and channel mapping can train. Header
quality checks reject declared missing samples and changed files. Compatibility
includes instrument/channel identity, sampling, units/scaling, gauge length,
sensitivities and available ROI/acquisition metadata. References cannot be applied
to arbitrary metrics or frequency bands; this version trains the four existing
metrics and the default 1–10 Hz band. Other bands remain raw-only until a matching
reference is implemented and trained.

Channel coordinates use exact masteliste keys or the existing verified-origin
interpolation, never interpolation across excluded fibre loops. Each located
channel uses its nearest forecast point within 5 km. The artifact records the
station assignment; station lids are never equated with instrument lids.

Calm requires wind ≤3 m/s and temperature >2°C, from the same forecast valid/issue
time. Valid time must be within two preceding hours; issue and collection must
both be no later than the signal frame. Null timestamp provenance, invalid
weather, and stale/missing forecasts exclude a training window. These are modeled
MET/YR values; calm selection is not a verified Normal Operations label.

At most one frame per minute per instrument is sampled. For each forecast region,
the latest 20% of calm hourly blocks (at least two blocks) are held out. Fitting
requires 120 frames across at least three hours and two UTC calendar dates.
MAD fitting tolerates occasional outliers but does not establish that the selected
reference is free of defects, ice, interference or gradual drift. Learning never
updates automatically during operation.

The JSON report records rules, weather evidence, station assignments, source-frame
identities, configuration, actual fitting dates, coverage and separate held-out
calm/windy score distributions. The NPZ contains channel IDs, eligibility,
fit counts and each metric's median/MAD/effective scale. Frames used for fitting
any channel in that configuration are conservatively marked **training reference**
in the UI. Historical scoring against a subsequently learned reference is
retrospective visualization, not a prospective detection backtest.

## First server reference: 2026-10-01

Reference `20261001T162737-3fa1d06a` sampled 4,029 frames from the verified archive.
Actual fitting coverage is September 29 18:13 UTC through October 1 13:59 UTC.
25,234 of 25,236 channels meet coverage rules; two have no qualifying geographic
forecast assignment. Station regions retained 407–2,147 fitting frames each and
73–568 held-out calm frames. All fitted AC RMS scales are positive.

Across channel/frame measurements, 10.35% of held-out calm scores exceeded 3,
compared with 32.61% of windy scores. At score 6 the proportions were 4.98% and
21.06%. These are descriptive comparison rates, not false-alarm or detection
accuracy estimates. Some forecast regions have substantial calm-period tails;
scores should guide review, and no alarm threshold is activated.

Audit: `results/calm-baseline-20261001/validation-summary.json`. A real archive
check verified identical map and investigation scores; source file identities
were checked against the read-only index after training. Existing live capture
configuration and event detection behavior are preserved.

Tests: `tests/test_calm.py`, existing metric/live/stitched/demo tests, the frontend
build and `scripts/check_calm_browser.py`. The browser check uses isolated fixtures
and exercises raw/calibrated switching, gaps, saturation, signal trends and mobile
layout without database writes.

## 8 m reference: 2026-10-14

Bundle `20261014T113058-77c8a057-bundle` retains the original 4 m reference and
adds references for both 8 m acquisition ranges. Training sampled 4,320 frames
from October 7–9 with the original wind/temperature and coverage requirements.
Actual fitting coverage is October 7 10:13 UTC through October 9 13:59 UTC.
The current range, which started October 13, had no qualifying calm frames in
the initial 27-hour search; that candidate was not activated.

The earlier 8 m files have the same instrument, gauge length, sample interval,
units, scaling, sensitivities, unwrapping range, ROI starts and decimation as the
current files. Only the ROI ends were shortened. An explicit projection retains
the current channel IDs and identical sensor distances, dropping source channels
68016, 68024, 101880 and 101888. No signal resampling or baseline interpolation is
performed. `train_calm.compatible_subset()` checks this narrow compatibility;
runtime scoring still requires an exact configuration fingerprint.

12,610 of the current 12,612 channels qualify, across all 16 assigned forecast
regions. The two channels without approved map positions remain unavailable.
The parent 8 m range qualifies 12,614 of 12,616 channels. Each station region
uses later hourly blocks for validation; all eligible metric scales are positive.
The bundle records separate fitting dates and source manifests for each
configuration so older recordings retain their original reference and dates.

On the parent acquisition grid, 18.20% of held-out calm AC RMS scores exceeded
3, versus 31.69% for windy periods; at score 6 these were 8.45% and 15.91%.
These are descriptive distributions, not false-alarm or detection accuracy.
The retained channels inherit unchanged per-channel fits; these aggregate
validation rates describe the parent grid. No event threshold is activated.

Audit and deployment evidence: `results/calm-baseline-20261014/`. Source-file
identities, forecast availability, chronological validation splits and the exact
channel projection were checked before activation. The old active manifest is
retained in the deployment rollback copy.
