import h5py
import numpy as np
import pytest

from src.Mapui.signals import inspect_recording, read_signal
from src.Mapui import stitched_signals as stitch


@pytest.fixture
def recordings(tmp_path,monkeypatch):
    monkeypatch.setenv('DAS_ARCHIVE_ROOT',str(tmp_path))
    records=[]
    for i in range(4):
        p=tmp_path/f'{i}.hdf5'
        time=np.arange(1000)*.01+i*10
        with h5py.File(p,'w') as f:
            f['data']=np.column_stack([np.sin(2*np.pi*3*time),np.cos(2*np.pi*7*time)])
            for k,v in dict(time=1000+i*10,dt=.01,channels=[100,104],unit='rad/(m*s)',dataScale=2,missingSamples=np.array([],dtype=int)).items():
                f['header/'+k]=v
        r=inspect_recording(p)
        r.update(id=i+1,lid=1,time_verified=False,processing='stored values × dataScale')
        records.append(r)
    monkeypatch.setattr(stitch,'rows',lambda *a:records)
    return records


def test_cross_file_window_matches_single_contiguous_recording(recordings,tmp_path):
    result=stitch.read_stitched_signal(recordings[1],100,-5,30,points=400)
    assert result['source_samples']==3000
    assert result['start']==-5 and result['end']==25
    assert len(result['source_files'])==4 and not result['truncated']
    time=np.arange(4000)*.01
    p=tmp_path/'whole.hdf5'
    with h5py.File(p,'w') as f:
        f['data']=np.column_stack([np.sin(2*np.pi*3*time),np.cos(2*np.pi*7*time)])
        for k,v in dict(time=1000,dt=.01,channels=[100,104],unit='rad/(m*s)',dataScale=2,missingSamples=np.array([],dtype=int)).items(): f['header/'+k]=v
    rec=inspect_recording(p);rec.update(id=9,processing='stored values × dataScale',time_verified=False)
    reference=read_signal(rec,100,5,30,400)
    for key in ['y','power','rms','variance','heat','channel_variance']:
        assert np.allclose(result[key],reference[key]),key
    assert np.allclose(result['x'],np.array(reference['x'])-10)


def test_archive_twenty_seconds_reads_next_file(recordings):
    r=stitch.read_stitched_signal(recordings[0],100,0,20)
    assert r['end']==20 and r['source_samples']==2000 and len(r['source_files'])==2


@pytest.mark.parametrize('kind',['gap','overlap','configuration'])
def test_does_not_bridge_discontinuities(recordings,kind):
    if kind=='gap': recordings[2]['acquisition_epoch']+=2
    elif kind=='overlap': recordings[2]['acquisition_epoch']-=2
    else: recordings[2]['unit']='other'
    r=stitch.read_stitched_signal(recordings[1],100,0,25)
    assert r['end']==10 and r['truncated']
    assert len(r['source_files'])==1


def test_archive_boundary_reported(recordings):
    r=stitch.read_stitched_signal(recordings[0],100,-10,30)
    assert r['start']==0 and r['end']==20 and r['truncated']


def test_changed_neighbor_is_not_used(recordings):
    recordings[2]['mtime_ns']+=1
    r=stitch.read_stitched_signal(recordings[1],100,0,20)
    assert r['end']==10 and 'changed' in r['stitch_note']


@pytest.mark.parametrize('field,value', [('gaugeLength',16.34), ('channels',[100,108])])
def test_stitch_stops_at_gauge_or_spacing_change(recordings, field, value):
    rec = recordings[2]
    path = stitch.safe_path(rec['relative_path'])
    with h5py.File(path, 'a') as f:
        if 'header/' + field in f:
            del f['header/' + field]
        f['header/' + field] = value
    rec.update(inspect_recording(path))
    result = stitch.read_stitched_signal(recordings[1],100,0,20)
    assert result['end'] == 10 and result['truncated']
    assert 'Acquisition configuration changes' in result['stitch_note']
