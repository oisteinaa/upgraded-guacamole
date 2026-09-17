# Test recording event review — 17 September 2026

384 sampled windows were analyzed: six consecutive 4.998-second windows across 64 blocks of 32 channels, using three local HDF5 recordings (about 30 seconds total). This is spatial sampling, not an exhaustive scan. Selected blocks are distinct; adjacent windows are not counted as separate incidents.

Signals use header dataScale and linear detrending, in rad/(m*s). Scores rank unusual patterns within this small sample; they are not class probabilities. No labels or candidate events were inserted into either database.

Header times are interpreted provisionally as Unix UTC; acquisition-time convention is unverified and no weather join was made. Geographic locations are not assigned. These four examples share one recording session and are not independent training examples.

| Candidate | Provisional UTC start (2026-06-16) | Header channels | Pattern | Dominant Hz | RMS |
| --- | --- | --- | --- | ---: | ---: |
| C1 | 00:00:09.772 | 81032–81156 (step 4) | Low-frequency oscillation | 0.60 | 4.52 |
| C2 | 00:00:29.764 | 19200–19324 (step 4) | Changing low-frequency vibration | 1.00 | 7.24 |
| C3 | 00:00:34.762 | 71432–71556 (step 4) | Changing localized tonal signal | 59.22 | 5.52 |
| C4 | 00:00:14.770 | 25600–25724 (step 4) | Persistent high-amplitude background | 47.02 | 151.15 |

Each shortlist window lasts 4.998 seconds. Exact zero-based, stop-exclusive sample slices and channel columns are in [shortlist.csv](shortlist.csv). All proposed classes remain hypotheses.

**C1: Low-frequency oscillation**

Check longer sustained oscillation and independently aligned wind/visual evidence; 0.6 Hz alone does not identify galloping.

- `000009.hdf5` samples [0, 2450), columns [20018, 20050).

**C2: Changing low-frequency vibration**

Compare adjacent windows and verify cable motion and wind. Could also be ordinary operation or another vibration source.

- `000019.hdf5` samples [4898, 4902), columns [4800, 4832).
- `000029.hdf5` samples [0, 2446), columns [4800, 4832).

**C3: Changing localized tonal signal**

Inspect raw signal quality and nearby activity. Persistent tones can arise from equipment or optical artifacts; no confirmed strike.

- `000029.hdf5` samples [2446, 4896), columns [17618, 17650).

**C4: Persistent high-amplitude background**

Check optical quality, wrapping, calibration and local machinery before assigning any physical class. This is a comparison region, not an established transient.

- `000009.hdf5` samples [2450, 4900), columns [6400, 6432).

The tonal block changes from a 27.21 Hz dominant peak in the first three windows to 59.22 Hz in the final three; RMS rises from 3.85 to 5.52. The high-amplitude comparison block remains at RMS 144.54–151.15 across all six windows, so it is not evidence of a new onset.

There is insufficient evidence here to label Ice Loading or Normal Operations. Human/field verification is required for every class; absence of an alarm does not establish normal operation.

Reproduce with:

```bash
.venv-map/bin/python -m src.Capture.event_discovery index .local/recordings results/event-review-20260917
.venv-map/bin/python -m src.Capture.event_discovery analyze results/event-review-20260917/index.json results/event-review-20260917 --window-seconds 5 --blocks 64 --channels-per-block 32
.venv-map/bin/python scripts/shortlist_test_events.py
```

The shortlist generator recreates shortlist.csv with blank labels; record verified annotations in review.csv before exporting training labels.
