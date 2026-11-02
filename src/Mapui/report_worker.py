"""Scheduled, restartable report generation. Run separately from the live service."""
import argparse,fcntl,json,os,traceback
from datetime import datetime,timezone
from psycopg2.extras import Json
import pandas as pd
from .db import database,rows
from .reports import report_root
from .report_rules import VERSION,periods,recurrence,finite_json,classify
from .report_analysis import analyze,preserve_evidence,screen
from .report_render import figures,render
from .report_ai import interpret

def persist(report_id,summary,histories,evidence):
    observations=[];mapping={}
    with database(write=True) as cur:
        cur.execute('SELECT * FROM report_findings ORDER BY id FOR UPDATE');all_findings=cur.fetchall()
        for m in summary['masts']:
            related=[f for f in all_findings if f['mast_id']==m['mast_id'] and f['family']==m['family']]
            active=next((f for f in related if f['status']!='closed'),None);closed=next((f for f in reversed(related) if f['status']=='closed'),None)
            assessment=None;f=active
            if active:assessment='continuing' if m['flagged'] else 'not_flagged' if m['week'].get('eligible') else 'unavailable'
            elif m['flagged']:
                allow=True
                if closed:
                    frame=pd.DataFrame(histories[m['mast_id']]);frame=frame[(frame.configuration==m['configuration'])&(frame.hour*3600>=closed['closed_at'].timestamp())]
                    post=screen(frame);post.update(configuration=m['configuration'],closure_reason=closed['closure_reason'],post_closure_qualified=post.get('wind_days',0)>=2 and post.get('wind_hours',0)>=8,flagged=classify(post) in ('red','yellow'))
                    allow=recurrence(closed['closure_observation'] or {},post)
                if allow:
                    cur.execute('''INSERT INTO report_findings(mast_id,family,priority,first_seen,last_seen,parent_id)
                      VALUES (%s,%s,%s,to_timestamp(%s),to_timestamp(%s),%s) RETURNING *''',(m['mast_id'],m['family'],m['priority'],max(summary['period_start'],m.get('first_epoch',summary['period_start'])),m.get('last_epoch',summary['actual_end']),closed['id'] if closed else None));f=cur.fetchone();assessment='recurrence' if closed else 'new'
                else:f=closed;assessment='suppressed'
            if f:
                if m['flagged'] and f['status']!='closed':
                    cur.execute('UPDATE report_findings SET last_seen=to_timestamp(%s),priority=%s WHERE id=%s',(m.get('last_epoch',summary['actual_end']),m['priority'],f['id']))
                mapping[m['mast_id']]=f['id'];observations.append(dict(finding_id=f['id'],assessment=assessment,metrics=m))
        # An existing family can be absent while another family is flagged at the same mast.
        seen={o['finding_id'] for o in observations}
        for f in all_findings:
            if f['status']=='closed' or f['id'] in seen:continue
            m=next((m for m in summary['masts'] if m['mast_id']==f['mast_id']),None)
            if m:observations.append(dict(finding_id=f['id'],assessment='unavailable',metrics=dict(m,flagged=False)))
        for o in observations:
            cur.execute('''INSERT INTO report_observations(report_id,finding_id,assessment,metrics) VALUES (%s,%s,%s,%s)
              ON CONFLICT(report_id,finding_id) DO NOTHING''',(report_id,o['finding_id'],o['assessment'],Json(o['metrics'])))
        for e in evidence:
            cur.execute('''INSERT INTO report_evidence(report_id,mast_id,finding_id,recording_id,source_epoch,channel,configuration,metadata,archive_path,sha256)
              VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(report_id,mast_id,recording_id,channel) DO NOTHING''',
              (report_id,e['mast_id'],mapping.get(e['mast_id']),e['recording_id'],e['source_epoch'],e['channel'],e['configuration'],Json(e['metadata']),f'{report_id}/{e["filename"]}',e['sha256']))
        cur.execute('UPDATE report_runs SET summary=%s WHERE id=%s',(Json(summary),report_id))
    return observations

def run(weekly=False,retry_ai=None):
    root=report_root();root.mkdir(parents=True,exist_ok=True)
    with (root/'.worker.lock').open('w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:print('Report worker already running');return
        week,end,start=periods(weekly=weekly);kind='weekly' if weekly else 'manual'
        if retry_ai is not None:
            found=rows('SELECT * FROM report_runs WHERE id=%s',(retry_ai,))
            if not found or not found[0]['summary'] or found[0]['kind']=='historical':raise ValueError('Select a completed numerical report')
            run=found[0];kind=run['kind'];week=run['period_start'];end=run['period_end']
        else:
            with database(write=True) as cur:
                cur.execute('''INSERT INTO report_runs(kind,period_start,period_end,rules_version) VALUES (%s,%s,%s,%s)
                  ON CONFLICT(kind,period_end,rules_version) DO NOTHING''',(kind,week,end,VERSION))
                cur.execute('SELECT * FROM report_runs WHERE kind=%s AND period_end=%s AND rules_version=%s',(kind,end,VERSION));run=cur.fetchone()
        report_id=run['id'];out=root/str(report_id);out.mkdir(exist_ok=True)
        if run['status']=='published' and retry_ai is None:print(f'Report {report_id} already published');return report_id
        print(f'Generating report {report_id}: {week.isoformat()} to {end.isoformat()}',flush=True)
        try:
            # Once observations are committed, resume the same snapshot after a renderer/AI failure.
            observations=rows('SELECT finding_id,assessment,metrics FROM report_observations WHERE report_id=%s',(report_id,))
            if run['summary']:
                summary=run['summary'];histories={int(k):v for k,v in json.loads((out/'hourly.json').read_text()).items()};evidence=json.loads((out/'preserved.json').read_text())
            else:
                summary,samples,requests,histories,configs=analyze(start,end,week,out);evidence=[];failures=[]
                for request in requests:
                    sample=samples[request['sample_index']]
                    try:
                        e=preserve_evidence(request,sample,out);e.update(mast_id=request['mast_id'],recording_id=sample['id'],source_epoch=sample['acquisition_epoch'],configuration=sample['configuration'],channel=request['channel']);evidence.append(e)
                    except (OSError,ValueError,KeyError) as exc:failures.append({'mast_id':request['mast_id'],'error':str(exc)})
                summary['evidence_failures']=failures
                for m in summary['masts']:
                    if m['flagged'] and not any(e['mast_id']==m['mast_id'] for e in evidence):m.update(flagged=False,priority='grey',eligible=False,evidence_error='Raw verification unavailable')
                (out/'preserved.json').write_text(json.dumps(finite_json(evidence),allow_nan=False))
                observations=persist(report_id,summary,histories,evidence)
            figs=figures(summary,histories,evidence,out)
            history=rows('''SELECT o.finding_id,r.period_end,r.rules_version,o.assessment,o.metrics FROM report_observations o JOIN report_runs r ON r.id=o.report_id WHERE o.finding_id=ANY(%s) AND o.report_id<>%s ORDER BY r.period_end DESC LIMIT 100''',([o['finding_id'] for o in observations],report_id)) if observations else []
            reviews=rows('SELECT finding_id,reviewer,action,note,created_at FROM report_finding_reviews WHERE finding_id=ANY(%s) ORDER BY id DESC LIMIT 100',([o['finding_id'] for o in observations],)) if observations else []
            compact=dict(summary);compact.pop('masts',None)
            packet=finite_json(dict(summary=compact,observations=observations,previous_observations=history,human_reviews=reviews))
            (out/'ai-input.json').write_text(json.dumps(packet,default=str,allow_nan=False))
            status,analysis,metadata=interpret(packet,[f['light'] for f in figs[:6]])
            render(report_id,summary,observations,status,analysis,figs,out,kind)
            with database(write=True) as cur:cur.execute("UPDATE report_runs SET status='published',published_at=now(),ai_status=%s,ai_analysis=%s,ai_metadata=%s,error=NULL WHERE id=%s",(status,Json(analysis),Json(metadata),report_id))
            print(f'Published report {report_id}; AI {status}; {len(observations)} finding observations',flush=True)
            return report_id
        except Exception as exc:
            with database(write=True) as cur:cur.execute("UPDATE report_runs SET status=CASE WHEN status='published' THEN status ELSE 'failed' END,error=%s WHERE id=%s",(str(exc)[:1000],report_id))
            raise

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--weekly',action='store_true');parser.add_argument('--retry-ai',type=int);args=parser.parse_args();run(args.weekly,args.retry_ai)
