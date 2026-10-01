"""Bounded signal windows across compatible, contiguous indexed recordings."""
from contextlib import ExitStack
import json
import math

import h5py
import numpy as np

from .db import rows
from .signals import safe_path, read_signal


def configuration(rec):
    path = safe_path(rec['relative_path'])
    stat = path.stat()
    if (stat.st_size, stat.st_mtime_ns) != (rec['size_bytes'], rec['mtime_ns']):
        raise ValueError('Recording changed; re-index before review')
    with h5py.File(path, 'r') as f:
        if 'header/missingSamples' not in f or f['header/missingSamples'].size:
            raise ValueError('Recording declares missing samples or lacks sample-quality metadata')
        extra = {}
        for name in ['header/gaugeLength','header/name','header/spatialUnwrRange','header/sensitivities','header/instrumentSerial','header/wavelength','demodSpec/roiStart','demodSpec/roiEnd','demodSpec/roiDec']:
            if name in f:
                value=f[name][()]
                extra[name]=value.decode() if isinstance(value,bytes) else np.asarray(value).tolist()
        if f['data'].shape != (rec['samples'],len(rec['channels'])):
            raise ValueError('Recording shape differs from index')
        if list(f['header/channels'][()]) != rec['channels'] or float(f['header/dt'][()]) != rec['dt'] or float(f['header/dataScale'][()]) != rec['scale']:
            raise ValueError('Recording metadata differs from index')
        extra['dtype']=str(f['data'].dtype)
    return (rec['dt'],rec['scale'],rec['unit'],rec['channels'],rec['lid'],rec['processing'],json.dumps(extra,sort_keys=True))


class JoinedData:
    def __init__(self, recordings):
        self.recordings=recordings

    def __enter__(self):
        self.stack=ExitStack()
        self.parts=[]
        offset=0
        try:
            for rec in self.recordings:
                f=self.stack.enter_context(h5py.File(safe_path(rec['relative_path']),'r'))
                self.parts.append((offset,offset+rec['samples'],f['data']))
                offset+=rec['samples']
        except BaseException:
            self.stack.close()
            raise
        return {'data':self}

    def __exit__(self,*args):
        return self.stack.__exit__(*args)

    def __getitem__(self,key):
        time,columns=key
        pieces=[]
        for lo,hi,data in self.parts:
            a,b=max(lo,time.start),min(hi,time.stop)
            if b>a: pieces.append(data[a-lo:b-lo,columns])
        return np.concatenate(pieces,axis=0)


def read_stitched_signal(recording, channel, start, duration, points=1600, **kwargs):
    if not math.isfinite(start) or not math.isfinite(duration) or duration<=0 or duration>600:
        raise ValueError('Select a finite window of up to 600 seconds')
    dt=recording['dt']
    epoch=recording['acquisition_epoch']
    # Include one analysis frame on each side; do not scan or open the full archive.
    candidates=rows('''SELECT * FROM das_recordings WHERE acquisition_epoch <= %s
        AND acquisition_epoch + samples*dt >= %s ORDER BY acquisition_epoch,id''',
        (epoch+start+duration+10, epoch+min(start,0)-10))
    candidates=[r for r in candidates if r['id']!=recording['id']]+[recording]
    candidates.sort(key=lambda r:(r['acquisition_epoch'],r['id']))
    index=next(i for i,r in enumerate(candidates) if r['id']==recording['id'])
    expected=configuration(recording)
    selected=[recording]
    stops=[]
    def compatible(left,right):
        gap=right['acquisition_epoch']-left['acquisition_epoch']-left['samples']*left['dt']
        if abs(gap)>dt+1e-6:
            return False,'Recording gap or overlap'
        try:
            if configuration(left)!=expected or configuration(right)!=expected:
                return False,'Acquisition configuration changes'
        except (ValueError,OSError,KeyError) as e:
            return False,str(e)
        return True,None
    for r in reversed(candidates[:index]):
        ok,reason=compatible(r,selected[0])
        if not ok:
            stops.append(reason);break
        selected.insert(0,r)
    for r in candidates[index+1:]:
        ok,reason=compatible(selected[-1],r)
        if not ok:
            stops.append(reason);break
        selected.append(r)
    offset=sum(r['samples'] for r in selected[:selected.index(recording)])*dt
    total=sum(r['samples'] for r in selected)
    virtual=dict(recording,samples=total,acquisition_epoch=epoch-offset,
                 time_verified=all(r['time_verified'] for r in selected))
    result=read_signal(virtual,channel,start+offset,duration,points,_source=JoinedData(selected),**kwargs)
    for rec in selected:
        stat = safe_path(rec['relative_path']).stat()
        if (stat.st_size, stat.st_mtime_ns) != (rec['size_bytes'], rec['mtime_ns']):
            raise ValueError('Recording changed during read; re-index before review')
    for field in ['start','end','duration','trend_start']:
        result[field]-=offset
    for field in ['x','trend_time','heat_time']:
        result[field]=[x-offset for x in result[field]]
    result['acquisition_epoch']=epoch
    result['requested_start']=start
    result['requested_end']=start+duration
    result['truncated']=result['start']>start+dt or result['end']<start+duration-dt
    result['source_files']=[]
    cursor=-offset
    for rec in selected:
        end=cursor+rec['samples']*dt
        if end>result['start'] and cursor<result['end']:
            result['source_files'].append(dict(recording_id=rec['id'],relative_path=rec['relative_path'],start=cursor,end=end))
        cursor=end
    result['stitch_note']=f"{len(result['source_files'])} recording files · contiguous samples; boundaries within one sample treated as timestamp rounding."
    if result['truncated']:
        result['stitch_note']+=' Requested context limited by '+('; '.join(sorted(set(stops))) if stops else 'archive boundary')+'.'
    from .calm import activity
    result["normalization"] = activity(selected, result["heat_channels"], result["start"], result["end"], epoch)
    return result
