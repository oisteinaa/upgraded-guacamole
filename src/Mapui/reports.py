"""Reports and human review API. AI never invokes mutation endpoints."""
import hashlib,json,os
from datetime import datetime,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from fastapi import APIRouter,HTTPException
from fastapi.responses import FileResponse,Response
from pydantic import BaseModel,Field
from psycopg2.extras import Json
from .db import rows,database,ROOT

router=APIRouter(prefix='/api/reports',tags=['reports'])
def report_root():return Path(os.getenv('DAS_REPORT_ROOT',ROOT/'.local/reports')).resolve()
def writable():
    if os.getenv('DAS_REVIEW_WRITES','1')!='1':raise HTTPException(403,'Review writes are disabled')
def nonblank(s,label):
    if not s.strip():raise HTTPException(422,label+' is required')
    return s.strip()
def get_one(sql,args=()):
    result=rows(sql,args)
    if not result:raise HTTPException(404,'Not found')
    return result[0]

@router.get('')
def list_reports():
    return {'items':rows('SELECT id,kind,period_start,period_end,status,created_at,published_at,ai_status,error,summary - \'masts\' AS summary FROM report_runs ORDER BY period_end DESC,id DESC LIMIT 100')}

@router.get('/findings')
def list_findings(status:str='active'):
    if status not in ('active','closed','all'):raise HTTPException(422,'Invalid status')
    clause="WHERE f.status<>'closed'" if status=='active' else "WHERE f.status='closed'" if status=='closed' else ''
    return {'items':rows('''SELECT f.*,m.route,m.mast,m.latitude,m.longitude,c.name AS class_name,l.event_id
        FROM report_findings f JOIN masts m ON m.id=f.mast_id
        LEFT JOIN event_classes c ON c.classid=f.classid LEFT JOIN report_event_links l ON l.finding_id=f.id '''+clause+" ORDER BY CASE f.priority WHEN 'red' THEN 0 ELSE 1 END,f.last_seen DESC,f.id DESC LIMIT 1000")}

@router.get('/findings/{finding_id}')
def finding_detail(finding_id:int):
    f=get_one('''SELECT f.*,m.route,m.mast,c.name AS class_name,l.event_id FROM report_findings f
       JOIN masts m ON m.id=f.mast_id LEFT JOIN event_classes c ON c.classid=f.classid
       LEFT JOIN report_event_links l ON l.finding_id=f.id WHERE f.id=%s''',(finding_id,))
    f['observations']=rows('SELECT o.*,r.period_end FROM report_observations o JOIN report_runs r ON r.id=o.report_id WHERE o.finding_id=%s ORDER BY r.period_end DESC',(finding_id,))
    f['reviews']=rows('SELECT * FROM report_finding_reviews WHERE finding_id=%s ORDER BY id DESC',(finding_id,))
    f['evidence']=rows('''SELECT e.*,t.classid AS training_classid,t.active AS training_active FROM report_evidence e
      LEFT JOIN report_training_labels t ON t.evidence_id=e.id WHERE e.finding_id=%s ORDER BY e.source_epoch DESC''',(finding_id,))
    return f

class Review(BaseModel):
    revision:int=Field(ge=0)
    reviewer:str=Field(min_length=1,max_length=100)
    note:str=Field(min_length=1,max_length=10000)
    action:str
    classid:int|None=None
    inconclusive:bool=False
    closure_reason:str|None=None
    verification_evidence:str|None=None
    evidence_ids:list[int]=Field(default_factory=list,max_length=100)

@router.post('/findings/{finding_id}/reviews')
def review_finding(finding_id:int,body:Review):
    writable();reviewer=nonblank(body.reviewer,'Reviewer');note=nonblank(body.note,'Notes')
    if body.action not in ('note','investigate','close','verify','revoke_verification'):raise HTTPException(422,'Invalid review action')
    with database(write=True) as cur:
        cur.execute('SELECT * FROM report_findings WHERE id=%s FOR UPDATE',(finding_id,));before=cur.fetchone()
        if not before:raise HTTPException(404,'Finding not found')
        if before['revision']!=body.revision:raise HTTPException(409,'Finding changed; reload before saving')
        if body.classid is not None:
            cur.execute('SELECT classid FROM event_classes WHERE classid=%s',(body.classid,))
            if not cur.fetchone():raise HTTPException(422,'Unknown classification')
        if body.action=='investigate':
            if before['status']=='closed':raise HTTPException(409,'Closed findings retain their closure; use a linked recurrence')
            cur.execute("UPDATE report_findings SET status='investigating' WHERE id=%s",(finding_id,))
        if body.action=='close':
            if before['status']=='closed':raise HTTPException(409,'Finding is already closed')
            if body.closure_reason not in ('repaired','expected_behaviour','sensing_artefact','duplicate','no_further_action'):raise HTTPException(422,'Select a closure reason')
            if (body.classid is None)==(not body.inconclusive):raise HTTPException(422,'Select exactly one classification or Inconclusive')
            cur.execute('SELECT metrics FROM report_observations WHERE finding_id=%s ORDER BY report_id DESC LIMIT 1',(finding_id,));last=cur.fetchone()
            cur.execute('''UPDATE report_findings SET status='closed',classid=%s,inconclusive=%s,closed_at=now(),closure_reason=%s,
             closure_note=%s,closure_observation=%s,verified=false WHERE id=%s''',(body.classid,body.inconclusive,body.closure_reason,note,Json(last['metrics'] if last else {}),finding_id))
        if body.action=='verify':
            if before['status']!='closed' or before['classid'] is None or before['inconclusive']:raise HTTPException(422,'Close with a classification before training verification')
            proof=nonblank(body.verification_evidence or '', 'Independent supporting evidence')
            if not body.evidence_ids:raise HTTPException(422,'Select the exact evidence windows to label')
            cur.execute('SELECT * FROM report_evidence WHERE id=ANY(%s) AND finding_id=%s',(body.evidence_ids,finding_id));evidence=cur.fetchall()
            if len(evidence)!=len(set(body.evidence_ids)):raise HTTPException(422,'Evidence does not belong to this finding')
            for e in evidence:
                path=(report_root()/(e['archive_path'] or '')).resolve()
                if not e['archive_path'] or not path.is_relative_to(report_root()) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=e['sha256']:raise HTTPException(422,'Verified training requires preserved, checksum-valid evidence')
                cur.execute('''INSERT INTO report_training_labels(evidence_id,classid,reviewer,verification_evidence) VALUES (%s,%s,%s,%s)
                 ON CONFLICT(evidence_id) DO UPDATE SET classid=EXCLUDED.classid,reviewer=EXCLUDED.reviewer,verification_evidence=EXCLUDED.verification_evidence,verified_at=now(),active=true''',(e['id'],before['classid'],reviewer,proof))
            cur.execute('UPDATE report_findings SET verified=true,verified_by=%s,verified_at=now(),verification_evidence=%s WHERE id=%s',(reviewer,proof,finding_id))
        if body.action=='revoke_verification':
            cur.execute('UPDATE report_findings SET verified=false WHERE id=%s',(finding_id,));cur.execute('UPDATE report_training_labels SET active=false WHERE evidence_id IN (SELECT id FROM report_evidence WHERE finding_id=%s)',(finding_id,))
        cur.execute('UPDATE report_findings SET revision=revision+1 WHERE id=%s RETURNING *',(finding_id,));after=cur.fetchone()
        after=dict(after,evidence_ids=body.evidence_ids)
        cur.execute('INSERT INTO report_finding_reviews(finding_id,reviewer,action,note,before_state,after_state) VALUES (%s,%s,%s,%s,%s,%s)',(finding_id,reviewer,body.action,note,Json(before,dumps=lambda v:json.dumps(v,default=str)),Json(after,dumps=lambda v:json.dumps(v,default=str))))
    return finding_detail(finding_id)

class Promote(BaseModel):
    revision:int=Field(ge=0)
    reviewer:str=Field(min_length=1,max_length=100)
    note:str=Field(min_length=1,max_length=10000)
    evidence_id:int
    classid:int|None=None
    event_id:int|None=None

@router.post('/findings/{finding_id}/event')
def promote(finding_id:int,body:Promote):
    writable();reviewer=nonblank(body.reviewer,'Reviewer');note=nonblank(body.note,'Investigation conclusion')
    with database(write=True) as cur:
        cur.execute('SELECT * FROM report_findings WHERE id=%s FOR UPDATE',(finding_id,));f=cur.fetchone()
        if not f:raise HTTPException(404,'Finding not found')
        cur.execute('SELECT event_id FROM report_event_links WHERE finding_id=%s',(finding_id,));old=cur.fetchone()
        if old:return dict(old)
        if f['revision']!=body.revision:raise HTTPException(409,'Finding changed; reload before saving')
        cur.execute('SELECT * FROM report_evidence WHERE id=%s AND finding_id=%s',(body.evidence_id,finding_id));e=cur.fetchone()
        if not e:raise HTTPException(422,'Select source evidence from this finding')
        if body.classid is not None:
            cur.execute('SELECT classid FROM event_classes WHERE classid=%s',(body.classid,))
            if not cur.fetchone():raise HTTPException(422,'Unknown class')
        if body.event_id:
            cur.execute('SELECT id FROM events WHERE id=%s',(body.event_id,))
            if not cur.fetchone():raise HTTPException(422,'Existing event not found')
            event_id=body.event_id
        else:
            if body.classid is None:raise HTTPException(422,'Select a reviewed classification before creating an event')
            cur.execute("SELECT data_type FROM event_data_types WHERE name='rms'");metric=cur.fetchone()
            if not metric:raise HTTPException(422,'RMS metric lookup is missing')
            value=e['metadata'].get('rms')
            if value is None:raise HTTPException(422,'Source evidence has no measured RMS')
            t=datetime.fromtimestamp(e['source_epoch'],timezone.utc).astimezone(ZoneInfo('Europe/Oslo')).replace(tzinfo=None)
            cur.execute('INSERT INTO events(time,type,value,comment,classid) VALUES (%s,%s,%s,%s,%s) RETURNING id',(t,metric['data_type'],value,f'Report finding {finding_id}: {f["family"]}'[:80],body.classid));event_id=cur.fetchone()['id']
            # Acquisition channel IDs need not exist on the geometry grid. Do not forge a geometry FK or alignment flag.
            cur.execute('INSERT INTO event_context(event_id,recording_id,start_sample,stop_sample,alignment_verified,evidence) VALUES (%s,%s,0,%s,false,%s)',(event_id,e['recording_id'],e['metadata'].get('samples'),json.dumps(dict(report_finding=finding_id,evidence_id=e['id'],source_epoch=e['source_epoch'],acquisition_channel=e['channel'],configuration=e['configuration'],reviewer=reviewer,note=note,processing=e['metadata'].get('processing')))))
            cur.execute('INSERT INTO event_reviews(event_id,previous_classid,classid,reviewer,note) VALUES (%s,NULL,%s,%s,%s)',(event_id,body.classid,reviewer,note))
        cur.execute('INSERT INTO report_event_links(finding_id,event_id,evidence_id,reviewer,note) VALUES (%s,%s,%s,%s,%s)',(finding_id,event_id,e['id'],reviewer,note))
        cur.execute('UPDATE report_findings SET revision=revision+1 WHERE id=%s',(finding_id,))
    return {'event_id':event_id}

@router.get('/training-export')
def training_export():
    labels=rows('''SELECT t.*,e.finding_id,e.source_epoch,e.configuration,e.channel,e.archive_path,e.sha256,e.metadata,c.name AS label
      FROM report_training_labels t JOIN report_evidence e ON e.id=t.evidence_id JOIN event_classes c ON c.classid=t.classid
      WHERE t.active ORDER BY e.finding_id,e.source_epoch''')
    return {'format':'verified-preserved-windows-v1','items':labels,'note':'Group all related finding/recurrence episodes and recording sessions together; never split a source recording between train and validation.'}

@router.get('/training-export.zip')
def training_zip():
    """Verified windows, with leakage-safe connected episode/recording groups."""
    import csv,io,zipfile
    labels=rows("""SELECT t.*,e.*,c.name AS label FROM report_training_labels t
      JOIN report_evidence e ON e.id=t.evidence_id JOIN event_classes c ON c.classid=t.classid
      WHERE t.active ORDER BY e.id""")
    if len(labels)>500:raise HTTPException(413,'Export exceeds 500 windows; use a scoped offline export')
    parents={f['id']:f['parent_id'] for f in rows('SELECT id,parent_id FROM report_findings')}
    def episode(fid):
        while parents.get(fid):fid=parents[fid]
        return fid
    union={}
    def root(k):
        union.setdefault(k,k)
        if union[k]!=k:union[k]=root(union[k])
        return union[k]
    for e in labels:
        a,b=root('finding-'+str(episode(e['finding_id']))),root('recording-'+str(e['recording_id']))
        union[b]=a
        day=datetime.fromtimestamp(e['source_epoch'],timezone.utc).date().isoformat()
        union[root('session-'+day)]=root(a)
    fields=['path','start_sample','stop_sample','channel_start','channel_stop','sample_rate_hz','label','group','configuration','temperature','wind_speed','wind_direction','humidity','sha256','evidence_id','reviewer','verification_evidence']
    output=io.BytesIO();manifest=io.StringIO();writer=csv.DictWriter(manifest,fieldnames=fields);writer.writeheader();total=0
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for e in labels:
            path=(report_root()/(e['archive_path'] or '')).resolve()
            if not path.is_relative_to(report_root()) or not path.is_file():raise HTTPException(409,'Preserved evidence missing')
            total+=path.stat().st_size
            if total>256*1024*1024:raise HTTPException(413,'Export exceeds 256 MB')
            data=path.read_bytes()
            if hashlib.sha256(data).hexdigest()!=e['sha256']:raise HTTPException(409,'Evidence checksum mismatch')
            name=f'evidence/{e["id"]}.npz';archive.writestr(name,data);m=e['metadata']
            writer.writerow(dict(path=name,start_sample=0,stop_sample=m['samples'],channel_start=0,channel_stop=m['channels'],sample_rate_hz=m['sample_rate_hz'],label=e['label'],group=root('finding-'+str(episode(e['finding_id']))),configuration=e['configuration'],sha256=e['sha256'],evidence_id=e['id'],reviewer=e['reviewer'],verification_evidence=e['verification_evidence'],**(m.get('weather') or {})))
        archive.writestr('manifest.csv',manifest.getvalue())
        archive.writestr('README.txt','Only explicitly verified windows. Keep groups intact in every split. Train separately per configuration; source data are raw, and the NPZ loader applies stored scale. No model is trained or activated by exporting.\n')
    return Response(output.getvalue(),media_type='application/zip',headers={'Content-Disposition':'attachment; filename="verified-report-training.zip"'})

@router.get('/evidence/{evidence_id}/download')
def evidence_download(evidence_id:int):
    e=get_one('SELECT archive_path,sha256 FROM report_evidence WHERE id=%s',(evidence_id,));path=(report_root()/(e['archive_path'] or '')).resolve()
    if not e['archive_path'] or not path.is_relative_to(report_root()) or not path.is_file():raise HTTPException(404,'Preserved evidence unavailable')
    if hashlib.sha256(path.read_bytes()).hexdigest()!=e['sha256']:raise HTTPException(409,'Evidence checksum mismatch')
    return FileResponse(path,filename=path.name)

@router.get('/{report_id}/html')
def report_html(report_id:int):
    get_one("SELECT id FROM report_runs WHERE id=%s AND status='published'",(report_id,));path=report_root()/str(report_id)/'report.html'
    if not path.is_file():raise HTTPException(404,'Report artifact unavailable')
    return FileResponse(path,media_type='text/html',headers={'Content-Security-Policy':"default-src 'none'; img-src data:; style-src 'unsafe-inline'; font-src data:; base-uri 'none'; frame-ancestors 'self'"})

@router.get('/{report_id}')
def report_detail(report_id:int):
    r=get_one('SELECT * FROM report_runs WHERE id=%s',(report_id,))
    r['observations']=rows('''SELECT o.*,f.status,f.priority,f.mast_id,m.route,m.mast,m.latitude,m.longitude,f.family
      FROM report_observations o JOIN report_findings f ON f.id=o.finding_id JOIN masts m ON m.id=f.mast_id
      WHERE o.report_id=%s ORDER BY CASE o.assessment WHEN 'new' THEN 0 WHEN 'recurrence' THEN 1 ELSE 2 END,o.finding_id''',(report_id,))
    return r
