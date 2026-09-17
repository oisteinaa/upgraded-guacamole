"""Select diverse review candidates and verify their HDF5 features; never label events."""
import argparse
import csv
import importlib.util
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    out = args.directory.resolve()
    spec = importlib.util.spec_from_file_location('discovery', out / 'event_discovery.py')
    discovery = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(discovery)
    index = json.loads((out / 'index.json').read_text())
    rows = list(csv.DictReader((out / 'review.csv').open()))
    blocks = defaultdict(list)
    for row in rows:
        blocks[(row['config'], row['channel_start'])].append(row)
    for block in blocks.values():
        baseline = float(np.median([float(r['rms']) for r in block]))
        for row in block:
            row['rms_to_block_median'] = float(row['rms']) / baseline if baseline else 0.
            row['low_frequency_fraction'] = sum(float(row[k]) for k in ['power_0.1_0.5_hz', 'power_0.5_1_hz', 'power_1_3_hz'])
    selectors = [
        ('Largest relative amplitude rise', lambda r: r['rms_to_block_median'],
         'Review onset, persistence and adjacent channels; investigate interference or optical artifacts.'),
        ('Strongest low-frequency fraction', lambda r: r['low_frequency_fraction'],
         'Review sustained cable oscillation and independently aligned wind/visual evidence before considering Wind Galloping.'),
        ('Most unusual remaining pattern', lambda r: float(r['anomaly_score']),
         'Inspect spectrum and raw signal quality; anomaly score is not a class probability.'),
        ('Largest remaining crest factor', lambda r: float(r['crest_factor']),
         'Review isolated pulses versus persistent tones, wrapping or poor optical signal before considering External Interference.'),
        ('Highest remaining amplitude', lambda r: float(r['rms']),
         'Compare full-session baseline and sensor quality; high amplitude alone does not establish a physical event.'),
    ]
    selected, used = [], set()
    for title, score, evidence in selectors:
        available = [r for r in rows if (r['config'], r['channel_start']) not in used]
        if not available:
            break
        row = dict(max(available, key=score))
        used.add((row['config'], row['channel_start']))
        row.update(candidate_id=f'S{len(selected)+1}', selection_reason=title,
                   evidence_needed=evidence, label='', label_verified='false')
        config = index['configurations'][row['config']]
        signal = discovery.read_signal({'refs': json.loads(row['refs'])}, config,
                                       int(row['channel_start']), int(row['channel_stop']))
        measured = discovery.features(signal, config['dt'])
        for name, value in measured.items():
            if not np.isclose(value, float(row[name]), rtol=1e-10):
                raise ValueError(f"Feature mismatch: {row['candidate_id']} {name}")
        selected.append(row)
    discovery.write_csv(out / 'shortlist.csv', selected)
    context = [dict(candidate_id=s['candidate_id'], **r)
               for s in selected for r in sorted(blocks[(s['config'], s['channel_start'])], key=lambda r: float(r['start_epoch']))]
    discovery.write_csv(out / 'shortlist-context.csv', context)
    summary = json.loads((out / 'summary.json').read_text())
    lines = ['# Server test-data review — 17 September 2026', '',
             f"Analyzed {len(index['files'])} files from `{index['root']}`: {summary['selected_windows']} temporal windows and {len(rows):,} signal feature rows. Each window is {float(rows[0]['duration_seconds']):.5f} seconds, with 64 sampled blocks of 32 channels. This covers the available temporal windows, not every spatial channel.", '',
             'Five distinct channel blocks were selected by complementary measurements. These are review candidates, not confirmed incidents; no event classes or database rows were written. Exact source file/sample references are in [shortlist.csv](shortlist.csv), and each selected block’s full timeline is in [shortlist-context.csv](shortlist-context.csv).', '',
             'Header times below use an unverified Unix UTC interpretation. No weather join or geographic assignment was made. Values use dataScale and linear detrending, in rad/(m*s); signals are not converted to cable displacement. All candidates from the same acquisition session must remain grouped for training.', '',
             '| ID | Provisional UTC start | Header channel range (step 4) | Selection | Peak Hz | RMS / block median |',
             '| --- | --- | --- | --- | ---: | ---: |']
    for row in selected:
        ids = json.loads(row['channel_ids'])
        time = datetime.fromtimestamp(float(row['start_epoch']), timezone.utc).isoformat(timespec='milliseconds')
        lines.append(f"| {row['candidate_id']} | {time} | {ids[0]}–{ids[-1]} | {row['selection_reason']} | {float(row['dominant_hz']):.2f} | {row['rms_to_block_median']:.2f}× |")
    for row in selected:
        block = blocks[(row['config'], row['channel_start'])]
        lines += ['', f"**{row['candidate_id']} — {row['selection_reason']}**", '', row['evidence_needed'], '',
                  f"RMS {float(row['rms']):.3f}; crest factor {float(row['crest_factor']):.2f}; fraction of spectral power at 0.1–3 Hz {row['low_frequency_fraction']:.1%}. This block's RMS across the archive ranges from {min(float(r['rms']) for r in block):.3f} to {max(float(r['rms']) for r in block):.3f}.", '']
        for ref in json.loads(row['refs']):
            lines.append(f"- `{ref['path']}` samples [{ref['start_sample']}, {ref['stop_sample']}), columns [{row['channel_start']}, {row['channel_stop']}).")
    lines += ['', 'All sample and column bounds are zero-based and stop-exclusive. Every shortlisted HDF5 slice was reread and every signal feature recomputed successfully (rtol=1e-10). Labels remain blank and unverified. This sample does not establish Ice Loading, Normal Operations, galloping or a vegetation strike without independent evidence.', '',
              'Recreate the shortlist with `python shortlist_server_events.py /home/inst/event-review-20260917`. This recreates the shortlist with blank labels; keep verified annotations in review.csv.']
    (out / 'README.md').write_text('\n'.join(lines) + '\n')
    discovery.write_json(out / 'shortlist-validation.json', dict(candidates=len(selected), reread_features_match=True, rtol=1e-10, labels_verified=False))
    print('\n'.join(lines[:16]))


if __name__ == '__main__':
    main()
