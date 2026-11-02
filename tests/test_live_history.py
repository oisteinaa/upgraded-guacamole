"""Acquisition-time retention, repeat publication and independent raw/calm peaks."""
import json
import numpy as np
import pytest
from src.Mapui.live_history import merge_history, recording_history


def history(start=0, key='a'):
    return dict(key=key, channel_edges=[0,4,8], sample_interval=.002, unit='u',
                rows=[dict(start=start,end=start+10,recording_id=int(start),raw=[1,2])])


def test_compact_live_updates_keep_only_new_history_and_preserve_disk(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from src.Mapui.api import app
    from src.Mapui.live import write_snapshot
    path = tmp_path / 'live.json'
    monkeypatch.setenv('DAS_LIVE_SNAPSHOT', str(path))
    saved = merge_history(history(0), history(10))
    write_snapshot(dict(points=[dict(rms=1)], heatmap={'values': [[1]]},
                        normalization={'heatmap': {'values': [[2]]}, 'profile': {'values': [3]}},
                        history=saved, acquisition_epoch=0, published_at=0,
                        replay=False, time_verified=True))
    original = path.read_bytes()
    with TestClient(app) as client:
        full = client.get('/api/live?compact=true').json()
        assert len(full['history']['rows']) == 2 and not full['history_delta']
        assert full['points'] == [] and 'heatmap' not in full
        assert full['normalization'] == {'profile': {'values': [3]}}
        delta = client.get('/api/live?compact=true&history_key=a&history_after=10').json()
        assert delta['history_delta'] and delta['history']['rows'] == saved['rows'][1:]
        assert delta['history_latest_end'] == 20
        same = client.get('/api/live?compact=true&history_key=a&history_after=20').json()
        assert same['history_delta'] and same['history']['rows'] == []
        for query in ['history_key=old&history_after=10', 'history_key=a&history_after=100']:
            reset = client.get('/api/live?compact=true&' + query).json()
            assert not reset['history_delta'] and len(reset['history']['rows']) == 2
        legacy = client.get('/api/live').json()
        assert legacy['history'] == saved and legacy['points'] == [dict(rms=1)]
        assert legacy['heatmap'] == {'values': [[1]]}
    assert path.read_bytes() == original


def test_retention_dedup_gaps_out_of_order_and_configuration():
    saved=None
    for start in range(0, 1100, 10):
        saved=merge_history(saved, history(start))
    assert len(saved['rows']) == 90
    assert saved['rows'][0]['start'] == 200
    assert merge_history(saved, history(1090)) == saved
    saved=merge_history(saved, history(1140))
    assert saved['rows'][-2]['end'] == 1100 and saved['rows'][-1]['start']==1140
    assert merge_history(saved, history(100)) == saved
    assert len(merge_history(saved,history(1150,key='new-config'))['rows'])==1
    # Overlap is not displayed as a synthetic stretched/interleaved row.
    assert len(merge_history(history(0),history(5))['rows'])==1


def test_atomic_snapshot_keeps_history_across_reload_and_duplicate_publish(tmp_path,monkeypatch):
    from src.Mapui.live import write_snapshot
    path=tmp_path/'live.json'
    monkeypatch.setenv('DAS_LIVE_SNAPSHOT',str(path))
    payload=dict(points=[],history_frames=history(0))
    write_snapshot(payload); write_snapshot(payload)
    assert len(json.loads(path.read_text())['history']['rows'])==1
    write_snapshot(dict(points=[],history_frames=history(20)))
    assert [r['start'] for r in json.loads(path.read_text())['history']['rows']]==[0,20]
    assert 'history_frames' not in json.loads(path.read_text())
    assert 'history_frames' in payload  # Caller may publish pending/final detection twice.


def test_demo_wrap_resets_history(tmp_path,monkeypatch):
    from src.Mapui.live import write_snapshot
    path=tmp_path/'demo.json';monkeypatch.setenv('DAS_LIVE_SNAPSHOT',str(path))
    for start in [100,110,0]:
        write_snapshot(dict(demo=True,acquisition_epoch=start,points=[],history_frames=history(start)))
    assert len(json.loads(path.read_text())['history']['rows'])==1


def test_frame_reduction_uses_exact_ten_second_metrics_and_independent_peaks(monkeypatch):
    from src.Mapui import calm,metrics,live_summary
    monkeypatch.setattr(calm,'fingerprint',lambda rec:'config')
    monkeypatch.setattr(calm,'reference',lambda *args:(dict(baseline_id='baseline'),dict(ac_rms_median=np.array([1.,2.,3.]))))
    monkeypatch.setattr(calm,'normalize_frame',lambda *args,**kw:({},np.array([5.,1.,np.nan])))
    monkeypatch.setattr(live_summary,'channel_groups',lambda ch:([np.array([0,1]),None,np.array([2])],[0,8,96,104]))
    def frame(rec,i):
        return dict(complete=i<2,start=i*10,end=min(i*10+10,25),values={'ac_rms':np.array([10.,30.,20.])})
    monkeypatch.setattr(metrics,'metric_frame',frame)
    rec=dict(id=1,lid=1,channels=[0,4,100],samples=2500,dt=.01,acquisition_epoch=1000,unit='u')
    result=recording_history(rec)
    assert [(r['start'],r['end']) for r in result['rows']]==[(1000,1010),(1010,1020)]
    row=result['rows'][0]
    assert row['raw']==[30.,None,20.] and row['raw_channels']==[4,None,100]
    assert row['calm']==[5.,None,None] and row['calm_channels']==[0,None,None]
    assert row['calm_raw']==[10.,None,None] and row['medians']==[1.,None,None]
    json.dumps(result,allow_nan=False)


def test_subsample_overlap_keeps_both_frames_but_real_overlap_is_rejected():
    first=history(100)
    second=history(109.99898)
    assert len(merge_history(first,second)['rows'])==2
    assert len(merge_history(first,history(109.99))['rows'])==1
