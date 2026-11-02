"""One-time, idempotent import of the October 22 report's unverified shortlist."""
import argparse,csv,json,shutil
from pathlib import Path
from datetime import datetime,timezone
from psycopg2.extras import Json
from src.Mapui.db import database
from src.Mapui.reports import report_root
from src.Mapui.report_render import render
from src.Mapui.report_rules import finite_json
p=argparse.ArgumentParser();p.add_argument('directory',type=Path);args=p.parse_args();source=args.directory
mapdata=json.loads((source/'mast-map-data.json').read_text());samples=json.loads((source/'sample.json').read_text())['samples']
metrics=list(csv.DictReader((source/'mast-screening.csv').open()));end=datetime(2026,10,22,tzinfo=timezone.utc);start=datetime(2026,9,22,tzinfo=timezone.utc)
masts=[]
for item in mapdata:
 old=next((r for r in metrics if int(r['mast_id'])==item['id'] and r['config'].startswith('2a756cef')),None)
 m=dict(mast_id=item['id'],route=item['route'],mast=item['mast'],latitude=item['latitude'],longitude=item['longitude'],priority=item['status'],flagged=item['status'] in ('red','yellow'),eligible=item['status']!='grey',family='impulsive_activity' if item['id']==385 else 'wind_response',configuration=old['config'] if old else None,import_note=item['reason'],unverified_import=True)
 for k in ('rho','gain','contrast_gain','wind_contrast'):
  try:m[k]=float(old[k]) if old else None
  except ValueError:m[k]=None
 masts.append(finite_json(m))
summary=dict(period_start=start.timestamp(),period_end=end.timestamp(),requested_start=start.timestamp(),actual_start=min(s['acquisition_epoch'] for s in samples),actual_end=max(s['acquisition_epoch'] for s in samples)+10,usable_windows=len(samples),selected_windows=len(samples),missing_windows=0,masts=masts,limitations=['Historical October 22 screening, imported without verifying defect classifications or training labels.','Source retention limits actual coverage; original report remains at /assets/power-line-integrity-20261022.html.','Review colours identify screening candidates, not structural safety.'])
with database(write=True) as c:
 c.execute("SELECT id FROM report_runs WHERE kind='historical' AND rules_version='october-20261022-import-v1'");existing=c.fetchone()
 if existing:print('Historical import already exists:',existing['id']);raise SystemExit(0)
 c.execute("INSERT INTO report_runs(kind,period_start,period_end,rules_version,summary,ai_status) VALUES ('historical',%s,%s,'october-20261022-import-v1',%s,'not_requested') RETURNING id",(start,end,Json(summary)));rid=c.fetchone()['id'];observations=[]
 for m in masts:
  if not m['flagged']:continue
  c.execute("SELECT id FROM report_findings WHERE mast_id=%s AND family=%s AND status<>'closed'",(m['mast_id'],m['family']));f=c.fetchone()
  if not f:
   c.execute("INSERT INTO report_findings(mast_id,family,priority,first_seen,last_seen) VALUES (%s,%s,%s,to_timestamp(%s),to_timestamp(%s)) RETURNING id",(m['mast_id'],m['family'],m['priority'],summary['actual_start'],summary['actual_end']));f=c.fetchone()
  c.execute("INSERT INTO report_observations(report_id,finding_id,assessment,metrics) VALUES (%s,%s,'new',%s)",(rid,f['id'],Json(m)));observations.append(dict(finding_id=f['id'],assessment='new',metrics=m))
 out=report_root()/str(rid);out.mkdir(parents=True,exist_ok=True)
 render(rid,summary,observations,'not requested',None,[],out,'historical')
 shutil.copyfile(source/'power-line-integrity-20261022.html',out/'original-report.html')
 c.execute("UPDATE report_runs SET status='published',published_at=now() WHERE id=%s",(rid,))
print('Imported historical report',rid,'with',len(observations),'unverified findings')
