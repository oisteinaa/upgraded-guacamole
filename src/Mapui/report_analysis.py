"""Read-only, bounded, reproducible weekly mast screening."""
import bisect,hashlib,json,os
from collections import defaultdict
from pathlib import Path
import h5py,numpy as np,pandas as pd
from scipy.stats import spearmanr
from psycopg2.extras import RealDictCursor
from .db import database,rows
from .signals import inspect_recording,safe_path
from .metrics import VERSION,metric_frame,fibre_positions,resolve_positions,interpolation_regions,geographic_distance
from .calm import fingerprint
from .report_rules import classify,finite_json


def query(sql,args=()):
    with database() as cur:
        cur.execute("SET LOCAL statement_timeout='120s'");cur.execute(sql,args);return list(cur.fetchall())

def screen(frame, bootstrap=False):
    """Each source hour contributes one observation, not three independent trials."""
    g=frame.replace([np.inf,-np.inf],np.nan).dropna(subset=['core','contrast','wind'])
    if g.empty:return {'eligible':False,'reason':'No valid weather/signal pairs'}
    calm=g[(g.wind<=3)&(g.temperature>2)];wind=g[g.wind>=8]
    qualified=len(calm)>=8 and len(wind)>=8 and calm.day.nunique()>=2 and wind.day.nunique()>=2
    def ratio(a,b):return float(a/b) if np.isfinite(b) and b>0 else None
    result=dict(eligible=qualified,hours=len(g),calm_hours=len(calm),wind_hours=len(wind),calm_days=int(calm.day.nunique()),wind_days=int(wind.day.nunique()),
      rho=float(spearmanr(g.wind,g.core)[0]) if len(g)>10 and g.wind.nunique()>1 and g.core.nunique()>1 else 0.,
      gain=ratio(wind.core.median(),calm.core.median()),contrast_gain=ratio(wind.contrast.median(),calm.contrast.median()),
      wind_contrast=float(wind.contrast.median()),first_epoch=float(g.hour.min()*3600),last_epoch=float(g.hour.max()*3600),weather_bins={})
    for key,part in g.groupby('weather_bin'):
        result['weather_bins'][str(key)]=dict(hours=len(part),days=int(part.day.nunique()),contrast=float(part.contrast.median()))
    # Whole-day descriptive sensitivity intervals, not defect probabilities.
    if qualified and bootstrap:
        rng=np.random.default_rng(20261023);days=[part for _,part in g.groupby('day')];ratios=[]
        for _ in range(200):
            boot=pd.concat([days[k] for k in rng.integers(0,len(days),len(days))]);a=boot[(boot.wind<=3)&(boot.temperature>2)].contrast.median();b=boot[boot.wind>=8].contrast.median()
            if a>0 and np.isfinite(b):ratios.append(b/a)
        if ratios:result['contrast_interval']=np.percentile(ratios,[2.5,97.5]).tolist()
    return finite_json(result)


def analyze(start,end,weekly_start,out):
    start,end,weekly_start=[v.timestamp() for v in (start,end,weekly_start)]
    catalog=query('''SELECT DISTINCT ON(floor(acquisition_epoch/1200)) id,relative_path,acquisition_epoch,dt,samples,lid,size_bytes,mtime_ns
     FROM das_recordings WHERE time_verified AND mapping_verified AND lid=1 AND acquisition_epoch>=%s AND acquisition_epoch<%s
     ORDER BY floor(acquisition_epoch/1200),acquisition_epoch,id''',(start,end))
    masts=query('SELECT id,route,mast,channel,lid,latitude,longitude,channel_distance_m FROM masts ORDER BY route,route_position')
    stations=query('SELECT lid,name,latitude,longitude FROM weather_stations ORDER BY lid')
    forecasts=query('''SELECT w.lid,t.abv,w.value,extract(epoch FROM w.source_time)::float8 valid,
      extract(epoch FROM w.forecast_updated_at)::float8 issued,extract(epoch FROM w.collected_at)::float8 collected
      FROM weather_obs w JOIN weather_obs_types t USING(type) WHERE w.source_time>=to_timestamp(%s) AND w.source_time<to_timestamp(%s)
      AND w.forecast_updated_at IS NOT NULL AND w.collected_at IS NOT NULL ORDER BY w.source_time,w.forecast_updated_at,w.collected_at''',(start-7200,end))
    weather={};times={}
    if forecasts:
        w=pd.DataFrame(forecasts);pairs=w.pivot_table(index=['lid','valid','issued'],columns='abv',values='value',aggfunc='last').join(w.groupby(['lid','valid','issued']).collected.max()).reset_index()
        for name in ['temp','wspd','wdir','rhum']:
            if name not in pairs:pairs[name]=np.nan
        pairs=pairs.dropna(subset=['temp','wspd','wdir','rhum'])
        for sid,g in pairs.groupby('lid'):
            weather[sid]=g.sort_values(['valid','issued','collected']).to_dict('records');times[sid]=[r['valid'] for r in weather[sid]]
    def weather_at(sid,epoch):
        for w in reversed(weather.get(sid,[])[:bisect.bisect_right(times.get(sid,[]),epoch)]):
            if epoch-w['valid']>7200:break
            if w['issued']<=epoch and w['collected']<=epoch and epoch-w['issued']<=43200:return w
        return None
    geometry=fibre_positions(1);configs={};samples=[];core=[];flanks=[];band=[];crest=[];exclusions=[];wind=[];temperature=[];direction=[];humidity=[];provenance=[]
    for n,item in enumerate(catalog):
        try:
            rec=query('SELECT * FROM das_recordings WHERE id=%s',(item['id'],))[0];path=safe_path(rec['relative_path']);actual=inspect_recording(path)
            for key in ['channels','samples','dt','scale','acquisition_epoch','size_bytes','mtime_ns']:
                if actual[key]!=rec[key]:raise ValueError('File/index mismatch '+key)
            if rec['samples']<round(10/rec['dt'])-1:raise ValueError('Incomplete ten-second source frame')
            key=fingerprint(rec)
            if key not in configs:
                located,_=resolve_positions(rec,geometry,interpolation_regions(rec,geometry));loc={x['recording_channel']:x for x in located};ch=np.array(rec['channels']);meta=[]
                near=np.zeros(len(ch),bool)
                for other in masts:
                    if other['channel_distance_m']<=10:near|=(abs(ch-other['channel'])*1.0213001907746815<24)
                for m in masts:
                    j=int(np.argmin(abs(ch-m['channel'])));position=loc.get(int(ch[j]));valid=position is not None and m['channel_distance_m']<=10 and geographic_distance(m,position)<=20
                    delta=(ch-ch[j])*1.0213001907746815;same=np.array([c in loc and position is not None and loc[c]['run']==position['run'] for c in ch]) if valid else np.zeros(len(ch),bool)
                    # Keep controls clear of other support neighbourhoods.
                    nearest=min(stations,key=lambda s:geographic_distance(m,s)) if stations else None
                    meta.append(dict(mast_id=m['id'],channel=int(ch[j]),valid=valid,core=np.flatnonzero(same&(abs(delta)<=16.5)).tolist(),
                      left=np.flatnonzero(same&~near&(delta>=-120)&(delta<=-48)).tolist(),right=np.flatnonzero(same&~near&(delta>=48)&(delta<=120)).tolist(),
                      station=nearest['lid'] if nearest and geographic_distance(m,nearest)<=5000 else None))
                configs[key]=dict(channels=len(ch),meta=meta,unit=rec['unit'],dt=rec['dt'],scale=rec['scale'],representative_path=rec['relative_path'])
            cfg=configs[key];stamp=path.stat();cachekey=hashlib.sha256(json.dumps([VERSION,str(path),stamp.st_size,stamp.st_mtime_ns,rec['dt'],rec['scale'],rec['channels'],0,1.,10.]).encode()).hexdigest()
            existing=Path(os.getenv('DAS_EXISTING_METRIC_CACHE',Path(__file__).resolve().parents[2]/'.local/metric-cache'))/(cachekey+'.npz')
            if existing.is_file():
                with np.load(existing,allow_pickle=False) as f:v={k:f[k].copy() for k in ['ac_rms','band_rms','peak']}
            else:v=metric_frame(rec)['values']
            def median(name,region):return np.array([np.median(v[name][m[region]]) if m[region] else np.nan for m in cfg['meta']])
            a=median('ac_rms','core');b=np.sqrt(median('ac_rms','left')*median('ac_rms','right'));pk=median('peak','core');br=median('band_rms','core')
            wx=[weather_at(m['station'],item['acquisition_epoch']) for m in cfg['meta']]
            core.append(a);flanks.append(b);crest.append(np.divide(pk,a,out=np.full_like(a,np.nan),where=a>0));band.append(br)
            for target,name in [(wind,'wspd'),(temperature,'temp'),(direction,'wdir'),(humidity,'rhum')]:target.append([w[name] if w else np.nan for w in wx])
            provenance.append([{k:w[k] for k in ['lid','valid','issued','collected']} if w else None for w in wx]);samples.append(dict(item,configuration=key))
        except (ValueError,OSError,KeyError) as exc:exclusions.append(dict(item,error=str(exc)))
        if n%100==0:print(f'Report samples {n+1}/{len(catalog)}; usable {len(samples)}',flush=True)
    if not samples:raise ValueError('No source recordings could be verified in this period')
    arrays={name:np.array(value) for name,value in [('core',core),('flank',flanks),('band',band),('crest',crest),('wind',wind),('temperature',temperature),('direction',direction),('humidity',humidity)]}
    np.savez_compressed(out/'metrics.npz',**arrays)
    (out/'sources.json').write_text(json.dumps(finite_json(dict(samples=samples,exclusions=exclusions,configurations=configs,weather=provenance)),allow_nan=False))
    identities=pd.DataFrame(samples);identities['hour']=(identities.acquisition_epoch//3600).astype(int);identities['day']=identities.hour//24
    results=[];histories={};requests=[]
    for j,m in enumerate(masts):
        df=identities[['id','acquisition_epoch','hour','day','configuration']].copy()
        for name,values in arrays.items():df[name]=values[:,j]
        df['contrast']=df.core/df.flank;df['sin']=np.sin(np.deg2rad(df.direction));df['cos']=np.cos(np.deg2rad(df.direction))
        h=df.groupby(['configuration','hour','day'],as_index=False)[['core','flank','band','crest','wind','temperature','sin','cos','contrast']].median()
        h['direction']=(np.rad2deg(np.arctan2(h.sin,h.cos))+360)%360
        h['weather_bin']=h.apply(lambda x:f'{int(x.wind//2)}:{int((x.direction+22.5)%360//45)}:{int(x.temperature//5)}' if np.isfinite([x.wind,x.direction,x.temperature]).all() else 'missing',axis=1)
        histories[m['id']]=h.to_dict('records')
        current_key=samples[-1]['configuration'];current=h[h.configuration==current_key];metric=screen(current);metric.update(configuration=current_key,mast_id=m['id'],route=m['route'],mast=m['mast'],latitude=m['latitude'],longitude=m['longitude'])
        week=current[current.hour*3600>=weekly_start];metric['week']=screen(week);metric['weekly_flagged']=classify(metric['week']) in ('red','yellow')
        # Do not report an old rolling-window flag as newly observed this week.
        metric['recent_support']=int(((week.wind>=8)&(week.contrast>=float(metric.get('wind_contrast') or 0)*.5)).sum())>=2 and week[week.wind>=8].day.nunique()>=2
        metric['priority']=classify(metric);metric['flagged']=metric['priority'] in ('red','yellow') and metric['recent_support']
        metric['family']='wind_response'
        if not metric['flagged']:
            impulses=week[(week.wind<=3)&(week.crest>=10)]
            if len(impulses)>=2 and impulses.day.nunique()>=2:metric.update(family='impulsive_activity',priority='yellow',flagged=True,impulse_hours=len(impulses))
        results.append(finite_json(metric))
        if metric['flagged']:
            candidate=df[(df.configuration==current_key)&(df.acquisition_epoch>=weekly_start)].copy()
            candidate=candidate[candidate.crest>=10].sort_values('crest',ascending=False) if metric['family']=='impulsive_activity' else candidate[candidate.wind>=8].sort_values('contrast',ascending=False)
            selected=candidate.drop_duplicates('day').head(2)
            for ix,row in selected.iterrows():requests.append(dict(mast_id=m['id'],sample_index=int(ix),channel=configs[current_key]['meta'][j]['channel'],core_columns=configs[current_key]['meta'][j]['core'],rms=float(row.core),family=metric['family'],weather={name:float(arrays[source][ix,j]) for name,source in [('temperature','temperature'),('wind_speed','wind'),('wind_direction','direction'),('humidity','humidity')]},weather_provenance=provenance[ix][j]))
    summary=dict(requested_start=start,period_start=weekly_start,period_end=end,selected_windows=len(catalog),usable_windows=len(samples),missing_windows=len(exclusions),measured_seconds=10*len(samples),
      actual_start=min(s['acquisition_epoch'] for s in samples),actual_end=max(s['acquisition_epoch'] for s in samples)+10,configurations={k:dict(channels=c['channels'],unit=c['unit']) for k,c in configs.items()},masts=results,
      limitations=['Sampled ten-second windows every twenty minutes; not continuous event surveillance.','Forecasts are modelled weather, not mast-mounted measurements.','Screening colours are not structural safety classifications.','No defect classification is established without human review.'])
    (out/'summary.json').write_text(json.dumps(finite_json(summary),allow_nan=False));(out/'hourly.json').write_text(json.dumps(finite_json(histories),allow_nan=False))
    return summary,samples,requests,histories,configs


def preserve_evidence(request,sample,out):
    """Preserve exact raw core-channel samples, plus scaled spectra for review."""
    from scipy.signal import welch
    rec=query('SELECT * FROM das_recordings WHERE id=%s',(sample['id'],))[0]
    if fingerprint(rec)!=sample['configuration']:raise ValueError('Evidence configuration changed')
    path=safe_path(rec['relative_path']);stamp=path.stat();cols=request['core_columns'];width=round(10/rec['dt'])
    if not cols:raise ValueError('No mast-neighbourhood channels')
    with h5py.File(path,'r') as f:data=f['data'][:width,cols]
    scaled=data.astype(float)*rec['scale'];ac=scaled-scaled.mean(axis=0);rms=float(np.median(np.sqrt(np.mean(ac**2,axis=0))))
    if not np.isclose(rms,request['rms'],rtol=1e-9):raise ValueError('Raw/cache RMS mismatch')
    freq,psd=welch(scaled,fs=1/rec['dt'],nperseg=min(4096,len(data)),detrend='linear',axis=0)
    filename=f'evidence-{request["mast_id"]}-{rec["id"]}.npz';dest=out/filename
    np.savez_compressed(dest,data=data,channels=np.array(rec['channels'])[cols],dt=rec['dt'],scale=rec['scale'],frequency=freq,psd=np.median(psd,axis=1))
    after=path.stat()
    if (stamp.st_size,stamp.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('Source changed during preservation')
    return dict(filename=filename,sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),metadata=finite_json(dict(rms=rms,samples=len(data),channels=len(cols),channel_ids=np.array(rec['channels'])[cols].tolist(),sample_rate_hz=1/rec['dt'],unit=rec['unit'],scale=rec['scale'],processing='stored raw samples; comparison RMS uses dataScale and mean removal',source_path=rec['relative_path'],source_size=stamp.st_size,source_mtime_ns=stamp.st_mtime_ns,source_time_verified=rec['time_verified'],source_mapping_verified=rec['mapping_verified'],weather=request.get('weather'),weather_provenance=request.get('weather_provenance'))))
