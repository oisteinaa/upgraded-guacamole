"""Run only against the dedicated disposable reporting test database."""
import os,tempfile,hashlib,io,zipfile,csv
from pathlib import Path
import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.Mapui.db import database
from src.Mapui.reports import router
assert 'sensnet_reports_test_20261023' in os.environ['DAS_DATABASE_URL']
root=Path(tempfile.mkdtemp());os.environ.update(DAS_REPORT_ROOT=str(root),DAS_REVIEW_WRITES='1')
with database(write=True) as c:
 c.execute("INSERT INTO report_runs(kind,period_start,period_end,rules_version,status) VALUES ('manual',now()-interval '7 days',now(),'test','published') RETURNING id");rid=c.fetchone()['id']
 c.execute("INSERT INTO report_findings(mast_id,family,priority,first_seen,last_seen) VALUES (1,'wind_response','red',now(),now()) RETURNING id");fid=c.fetchone()['id']
 c.execute("INSERT INTO report_observations(report_id,finding_id,assessment,metrics) VALUES (%s,%s,'new','{}')",(rid,fid))
 np.savez(root/'source.npz',data=np.ones((100,2)),scale=2.,dt=.01)
 sha=hashlib.sha256((root/'source.npz').read_bytes()).hexdigest()
 c.execute("""INSERT INTO report_evidence(report_id,mast_id,finding_id,recording_id,source_epoch,channel,configuration,metadata,archive_path,sha256) VALUES (%s,1,%s,1,1780000000,20,'A','{"rms":2,"samples":100,"channels":2,"sample_rate_hz":100}','source.npz',%s) RETURNING id""",(rid,fid,sha));eid=c.fetchone()['id']
app=FastAPI();app.include_router(router);client=TestClient(app)
base=f'/api/reports/findings/{fid}'
body=dict(revision=0,reviewer='Engineer',note='Inspection evidence',action='verify',evidence_ids=[eid],verification_evidence='Inspection ticket')
assert client.post(base+'/reviews',json=body).status_code==422
assert client.post(base+'/reviews',json=dict(body,action='close')).status_code==422
promotion=dict(revision=0,reviewer='Engineer',note='Observed response',evidence_id=eid,classid=3)
a=client.post(base+'/event',json=promotion);assert a.status_code==200,a.text
assert client.post(base+'/event',json=promotion).json()==a.json()
assert client.get(base).json()['status']=='open'
assert client.post(base+'/reviews',json=dict(body,action='note')).status_code==409
closed=client.post(base+'/reviews',json=dict(body,revision=1,action='close',closure_reason='repaired',classid=3));assert closed.status_code==200,closed.text
assert not closed.json()['verified']
assert client.get('/api/reports/training-export').json()['items']==[]
verify=client.post(base+'/reviews',json=dict(body,revision=2));assert verify.status_code==200,verify.text
export=client.get('/api/reports/training-export.zip');assert export.status_code==200,export.text
with zipfile.ZipFile(io.BytesIO(export.content)) as z:
 records=list(csv.DictReader(io.StringIO(z.read('manifest.csv').decode())));assert records[0]['label']=='Wind Galloping';assert records[0]['group'].startswith('finding-')
(root/'source.npz').write_bytes(b'corrupt')
assert client.get(f'/api/reports/evidence/{eid}/download').status_code==409
assert client.post(base+'/reviews',json=dict(body,revision=3)).status_code==422
assert client.post(base+'/reviews',json=dict(body,revision=3,action='revoke_verification')).status_code==200
assert client.get('/api/reports/training-export').json()['items']==[]
print('PASS: migration, classified closure, stale revision, idempotent event, independent verification, exact-window export, checksum protection and revocation')
