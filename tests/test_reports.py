import json
from datetime import datetime,timezone
from unittest.mock import patch
import pytest
from src.Mapui.report_rules import periods,recurrence,classify
from src.Mapui.report_ai import interpret

def test_schedule_uses_utc_week_across_dst():
    start,end,context=periods(datetime(2026,10,26,4,tzinfo=timezone.utc),weekly=True)
    assert end.isoformat()=='2026-10-26T00:00:00+00:00'
    assert (end-start).days==7 and (end-context).days==30

def test_screening_is_not_a_classification():
    assert classify({'eligible':False})=='grey'
    assert classify(dict(eligible=True,rho=.8,gain=10,contrast_gain=1.1,wind_contrast=3))=='green'
    assert classify(dict(eligible=True,rho=.8,gain=10,contrast_gain=3,wind_contrast=3))=='red'

def test_recurrence_requires_postclosure_matching_weather_and_configuration():
    old={'configuration':'A','weather_bins':{'4:2:1':{'hours':8,'days':2,'contrast':2}}}
    current={'configuration':'A','post_closure_qualified':True,'weather_bins':{'4:2:1':{'hours':8,'days':2,'contrast':4}}}
    assert recurrence(old,current)
    assert not recurrence(old,dict(current,configuration='B'))
    assert not recurrence(old,dict(current,post_closure_qualified=False))
    assert not recurrence(old,dict(current,weather_bins={'different':{'hours':8,'days':2,'contrast':40}}))

def test_ai_failure_preserves_numerical_report():
    with patch.dict('os.environ',{'OPENAI_API_KEY':''}):assert interpret({'observations':[]})[0]=='unavailable'
    with patch.dict('os.environ',{'OPENAI_API_KEY':'test'}),patch('httpx.post') as post:
        post.return_value.status_code=429
        assert interpret({'observations':[]})[0]=='unavailable'

def test_ai_cannot_invent_finding_references():
    with patch.dict('os.environ',{'OPENAI_API_KEY':'test'}),patch('httpx.post') as post:
        post.return_value.status_code=200
        post.return_value.json.return_value={'status':'completed','output':[{'content':[{'type':'output_text','text':json.dumps({'summary':'x','limitations':[],'findings':[{'finding_id':99}]})}]}]}
        assert interpret({'observations':[{'finding_id':1}]})[0]=='unavailable'

def test_preserved_npz_applies_scale_and_checks_bounds(tmp_path):
    import numpy as np
    from src.Capture.event_ml import read_window
    p=tmp_path/'evidence.npz';np.savez(p,data=np.ones((20,2)),scale=3.)
    assert np.all(read_window(p,0,10,0,2)==3)
    with pytest.raises(ValueError):read_window(p,0,21,0,2)

def test_manifest_rejects_configuration_mixing(tmp_path):
    from src.Capture.event_ml import load_manifest
    p=tmp_path/'manifest.csv';p.write_text('configuration,label,group\nA,Wind Galloping,one\nB,Wind Galloping,two\n')
    with pytest.raises(ValueError,match='incompatible'):load_manifest(p)

def test_report_router_is_importable():
    from src.Mapui.reports import router
    assert any(route.path=='/api/reports/findings/{finding_id}/event' for route in router.routes)

def test_ai_preserves_quota_code_without_error_body_or_key():
    with patch.dict('os.environ',{'OPENAI_API_KEY':'secret-value'}),patch('httpx.post') as post:
        post.return_value.status_code=429
        post.return_value.json.return_value={'error':{'code':'insufficient_quota','type':'insufficient_quota','message':'secret-value must never be stored'}}
        status,analysis,meta=interpret({'observations':[]})
        assert status=='unavailable' and analysis is None
        assert meta['error_code']=='insufficient_quota'
        assert 'secret-value' not in json.dumps(meta)
