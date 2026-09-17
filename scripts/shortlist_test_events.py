"""Build a review shortlist from the 2026-09-17 local discovery run; no DB writes."""
import csv
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/event-review-20260917'
rows = list(csv.DictReader((OUT / 'review.csv').open()))
# Select distinct channel blocks to avoid presenting adjacent windows as incidents.
choices = [
    (20018, 'power_0.5_1_hz', 'Low-frequency oscillation', 'Wind Galloping',
     'Check longer sustained oscillation and independently aligned wind/visual evidence; 0.6 Hz alone does not identify galloping.'),
    (4800, 'rms', 'Changing low-frequency vibration', 'Wind Galloping',
     'Compare adjacent windows and verify cable motion and wind. Could also be ordinary operation or another vibration source.'),
    (17618, 'anomaly_score', 'Changing localized tonal signal', 'External Interference',
     'Inspect raw signal quality and nearby activity. Persistent tones can arise from equipment or optical artifacts; no confirmed strike.'),
    (6400, 'rms', 'Persistent high-amplitude background', '',
     'Check optical quality, wrapping, calibration and local machinery before assigning any physical class. This is a comparison region, not an established transient.'),
]
selected = []
for i, (column, metric, pattern, hypothesis, evidence) in enumerate(choices, 1):
    block = [r for r in rows if int(r['channel_start']) == column]
    row = dict(max(block, key=lambda r: float(r[metric])))
    row.update(candidate_id=f'C{i}', observed_pattern=pattern, hypothesis=hypothesis,
               review_evidence_needed=evidence, label='', label_verified='false')
    selected.append(row)
with (OUT / 'shortlist.csv').open('w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=list(selected[0]))
    writer.writeheader()
    writer.writerows(selected)
lines = [
    '# Test recording event review — 17 September 2026', '',
    '384 sampled windows were analyzed: six consecutive 4.998-second windows across 64 blocks of 32 channels, using three local HDF5 recordings (about 30 seconds total). This is spatial sampling, not an exhaustive scan. Selected blocks are distinct; adjacent windows are not counted as separate incidents.', '',
    'Signals use header dataScale and linear detrending, in rad/(m*s). Scores rank unusual patterns within this small sample; they are not class probabilities. No labels or candidate events were inserted into either database.', '',
    'Header times are interpreted provisionally as Unix UTC; acquisition-time convention is unverified and no weather join was made. Geographic locations are not assigned. These four examples share one recording session and are not independent training examples.', '',
    '| Candidate | Provisional UTC start (2026-06-16) | Header channels | Pattern | Dominant Hz | RMS |',
    '| --- | --- | --- | --- | ---: | ---: |',
]
for row in selected:
    channels = json.loads(row['channel_ids'])
    time = datetime.fromtimestamp(float(row['start_epoch']), timezone.utc).strftime('%H:%M:%S.%f')[:-3]
    lines.append(f"| {row['candidate_id']} | {time} | {channels[0]}–{channels[-1]} (step 4) | {row['observed_pattern']} | {float(row['dominant_hz']):.2f} | {float(row['rms']):.2f} |")
lines += ['', 'Each shortlist window lasts 4.998 seconds. Exact zero-based, stop-exclusive sample slices and channel columns are in [shortlist.csv](shortlist.csv). All proposed classes remain hypotheses.', '']
for row in selected:
    lines += [f"**{row['candidate_id']}: {row['observed_pattern']}**", '', row['review_evidence_needed'], '']
    for ref in json.loads(row['refs']):
        lines.append(f"- `{Path(ref['path']).name}` samples [{ref['start_sample']}, {ref['stop_sample']}), columns [{row['channel_start']}, {row['channel_stop']}).")
    lines.append('')
lines += [
    'The tonal block changes from a 27.21 Hz dominant peak in the first three windows to 59.22 Hz in the final three; RMS rises from 3.85 to 5.52. The high-amplitude comparison block remains at RMS 144.54–151.15 across all six windows, so it is not evidence of a new onset.', '',
    'There is insufficient evidence here to label Ice Loading or Normal Operations. Human/field verification is required for every class; absence of an alarm does not establish normal operation.', '',
    'Reproduce with:', '', '```bash',
    '.venv-map/bin/python -m src.Capture.event_discovery index .local/recordings results/event-review-20260917',
    '.venv-map/bin/python -m src.Capture.event_discovery analyze results/event-review-20260917/index.json results/event-review-20260917 --window-seconds 5 --blocks 64 --channels-per-block 32',
    '.venv-map/bin/python scripts/shortlist_test_events.py', '```', '',
    'The shortlist generator recreates shortlist.csv with blank labels; record verified annotations in review.csv before exporting training labels.',
]
(OUT / 'README.md').write_text('\n'.join(lines) + '\n')
print('\n'.join(lines[:13]))
