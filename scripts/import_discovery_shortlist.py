#!/usr/bin/env python3
"""Import a discovery shortlist as unclassified queue items with explicit provenance."""
import argparse
import csv
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('shortlist', type=Path)
    parser.add_argument('--archive', required=True, type=Path)
    parser.add_argument('--apply', action='store_true', help='Commit validated candidates; otherwise roll back')
    args = parser.parse_args()
    archive = args.archive.resolve()
    rows = list(csv.DictReader(args.shortlist.open()))
    connection = psycopg2.connect(os.environ['DAS_DATABASE_URL'])
    report = []
    try:
        with connection.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout='10s'")
            cur.execute("SELECT pg_advisory_xact_lock(20260917, 1)")
            cur.execute("SELECT name FROM event_data_types WHERE data_type=1")
            if cur.fetchone() != ('rms',):
                raise ValueError('Expected metric 1 to be RMS')
            for row in rows:
                if row['label'].strip() or row['label_verified'].lower() not in ('', 'false'):
                    raise ValueError('Importer accepts unverified, unlabeled candidates only')
                refs = json.loads(row['refs'])
                recording_refs = []
                for ref in refs:
                    path = Path(ref['path']).resolve()
                    relative = str(path.relative_to(archive))
                    stat = path.stat()
                    if [stat.st_size, stat.st_mtime_ns] != ref['stamp']:
                        raise ValueError('Recording changed: ' + relative)
                    cur.execute('SELECT id,samples,channels,size_bytes,mtime_ns FROM das_recordings WHERE relative_path=%s', (relative,))
                    recording = cur.fetchone()
                    if recording is None or list(recording[3:]) != ref['stamp']:
                        raise ValueError('Missing or stale recording index: ' + relative)
                    lo, hi = int(row['channel_start']), int(row['channel_stop'])
                    if not (0 <= ref['start_sample'] < ref['stop_sample'] <= recording[1]):
                        raise ValueError('Invalid sample bounds')
                    if not (0 <= lo < hi <= len(recording[2])) or recording[2][lo:hi] != json.loads(row['channel_ids']):
                        raise ValueError('Channel IDs do not match recording index')
                    recording_refs.append((recording[0], ref))
                marker = 'discovery-window:' + row['window_id']
                cur.execute('SELECT event_id FROM event_context WHERE split_part(evidence,E\'\\n\',1)=%s', (marker,))
                existing = cur.fetchone()
                if existing:
                    report.append(dict(candidate=row['candidate_id'], event_id=existing[0], action='already present'))
                    continue
                value = float(row['rms'])
                if not math.isfinite(value):
                    raise ValueError('Invalid RMS')
                # Store provisional header UTC converted to Oslo, explicitly qualified in evidence.
                timestamp = datetime.fromtimestamp(float(row['start_epoch']), timezone.utc).astimezone(ZoneInfo('Europe/Oslo')).replace(tzinfo=None)
                comment = f"Review {row['candidate_id']}: {row['selection_reason']}"
                if len(comment) > 80:
                    raise ValueError('Comment exceeds event schema')
                evidence = marker + '\n' + (
                    'Unclassified discovery candidate. Time is provisional header Unix UTC converted to Europe/Oslo; '
                    'clock and geographic alignment are unverified. RMS is dataScale-adjusted and linearly detrended '
                    'in rad/(m*s), not the legacy alarm metric representation. '
                    'The context recording points to the longest constituent slice; the metric covers ALL refs below.\n'
                ) + json.dumps(row, ensure_ascii=False)
                cur.execute('INSERT INTO events(time,type,value,comment,classid) VALUES (%s,1,%s,%s,NULL) RETURNING id', (timestamp,value,comment))
                event_id = cur.fetchone()[0]
                recording_id, ref = max(recording_refs, key=lambda pair: pair[1]['stop_sample']-pair[1]['start_sample'])
                cur.execute('''INSERT INTO event_context(event_id,recording_id,start_sample,stop_sample,alignment_verified,evidence)
                               VALUES (%s,%s,%s,%s,false,%s)''',
                            (event_id,recording_id,ref['start_sample'],ref['stop_sample'],evidence))
                report.append(dict(candidate=row['candidate_id'], event_id=event_id, action='inserted' if args.apply else 'would insert'))
        if args.apply:
            connection.commit()
        else:
            connection.rollback()
    finally:
        connection.close()
    print(json.dumps(dict(committed=args.apply, events=report), indent=2))


if __name__ == '__main__':
    main()
