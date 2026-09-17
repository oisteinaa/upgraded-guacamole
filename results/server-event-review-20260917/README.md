# Server test-data review — 17 September 2026

Analyzed 90 files from `/home/inst/DataCopy`: 90 temporal windows and 5,760 signal feature rows. Each window is 9.99804 seconds, with 64 sampled blocks of 32 channels. This covers the available temporal windows, not every spatial channel.

Five distinct channel blocks were selected by complementary measurements. These are review candidates, not confirmed incidents; no event classes or database rows were written. Exact source file/sample references are in [shortlist.csv](shortlist.csv), and each selected block’s full timeline is in [shortlist-context.csv](shortlist-context.csv).

Header times below use an unverified Unix UTC interpretation. No weather join or geographic assignment was made. Values use dataScale and linear detrending, in rad/(m*s); signals are not converted to cable displacement. All candidates from the same acquisition session must remain grouped for training.

| ID | Provisional UTC start | Header channel range (step 4) | Selection | Peak Hz | RMS / block median |
| --- | --- | --- | --- | ---: | ---: |
| S1 | 2026-06-16T00:01:19.760+00:00 | 62336–62460 | Largest relative amplitude rise | 77.82 | 4.41× |
| S2 | 2026-06-16T00:00:49.764+00:00 | 19200–19324 | Strongest low-frequency fraction | 1.00 | 1.15× |
| S3 | 2026-06-16T00:01:19.760+00:00 | 69768–69892 | Most unusual remaining pattern | 189.94 | 1.25× |
| S4 | 2026-06-16T00:01:09.762+00:00 | 0–124 | Largest remaining crest factor | 100.02 | 0.88× |
| S5 | 2026-06-16T00:14:59.599+00:00 | 25600–25724 | Highest remaining amplitude | 4.50 | 1.14× |

**S1 — Largest relative amplitude rise**

Review onset, persistence and adjacent channels; investigate interference or optical artifacts.

RMS 27.352; crest factor 7.20; fraction of spectral power at 0.1–3 Hz 0.3%. This block's RMS across the archive ranges from 3.516 to 27.352.

- `/home/inst/DataCopy/000109.hdf5` samples [4896, 4902), columns [15584, 15616).
- `/home/inst/DataCopy/000119.hdf5` samples [0, 4895), columns [15584, 15616).

**S2 — Strongest low-frequency fraction**

Review sustained cable oscillation and independently aligned wind/visual evidence before considering Wind Galloping.

RMS 6.344; crest factor 5.34; fraction of spectral power at 0.1–3 Hz 88.0%. This block's RMS across the archive ranges from 3.779 to 10.220.

- `/home/inst/DataCopy/000039.hdf5` samples [4898, 4901), columns [4800, 4832).
- `/home/inst/DataCopy/000049.hdf5` samples [0, 4898), columns [4800, 4832).

**S3 — Most unusual remaining pattern**

Inspect spectrum and raw signal quality; anomaly score is not a class probability.

RMS 0.763; crest factor 41.78; fraction of spectral power at 0.1–3 Hz 0.1%. This block's RMS across the archive ranges from 0.601 to 0.763.

- `/home/inst/DataCopy/000109.hdf5` samples [4896, 4902), columns [17202, 17234).
- `/home/inst/DataCopy/000119.hdf5` samples [0, 4895), columns [17202, 17234).

**S4 — Largest remaining crest factor**

Review isolated pulses versus persistent tones, wrapping or poor optical signal before considering External Interference.

RMS 5.260; crest factor 17.50; fraction of spectral power at 0.1–3 Hz 0.0%. This block's RMS across the archive ranges from 4.931 to 6.668.

- `/home/inst/DataCopy/000059.hdf5` samples [4897, 4902), columns [0, 32).
- `/home/inst/DataCopy/000109.hdf5` samples [0, 4896), columns [0, 32).

**S5 — Highest remaining amplitude**

Compare full-session baseline and sensor quality; high amplitude alone does not establish a physical event.

RMS 152.385; crest factor 3.66; fraction of spectral power at 0.1–3 Hz 1.9%. This block's RMS across the archive ranges from 96.663 to 152.385.

- `/home/inst/DataCopy/001449.hdf5` samples [4817, 4902), columns [6400, 6432).
- `/home/inst/DataCopy/001459.hdf5` samples [0, 4816), columns [6400, 6432).

All sample and column bounds are zero-based and stop-exclusive. Every shortlisted HDF5 slice was reread and every signal feature recomputed successfully (rtol=1e-10). Labels remain blank and unverified. This sample does not establish Ice Loading, Normal Operations, galloping or a vegetation strike without independent evidence.

Recreate the shortlist with `python shortlist_server_events.py /home/inst/event-review-20260917`. This recreates the shortlist with blank labels; keep verified annotations in review.csv.

Queue import: all five candidates were imported into server `sensnetdb` on
2026-09-17 as unclassified RMS review items: S1=115848, S2=115849,
S3=115850, S4=115851, S5=115852. The server GUI reads these database rows.
Times use the provisional header Unix UTC interpretation converted to Oslo.
Full source-window provenance is retained in `event_context.evidence`; its
single recording reference points to the longest constituent slice. Alignment
remains unverified, so these records do not claim verified map locations.
Importer: `scripts/import_discovery_shortlist.py`; repeat imports skip existing
window IDs and preserve reviews. The archive analysis itself did not write rows;
this import is the subsequent queue-population step.
