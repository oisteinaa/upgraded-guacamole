"""Self-contained house report; numerical evidence remains readable without AI."""
import base64,html,io,json
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from .report_style import RC,palette,frame
for font in Path(__file__).with_name('report_assets').glob('*.ttf'):matplotlib.font_manager.fontManager.addfont(font)
plt.rcParams.update(RC)
esc=lambda value:html.escape(str(value))
def date(epoch):return datetime.fromtimestamp(epoch,timezone.utc).strftime('%d %b %Y %H:%M UTC')
def number(v):return '—' if v is None else f'{v:.2f}'
def uri(fig):
    b=io.BytesIO();fig.savefig(b,format='png',dpi=135,bbox_inches='tight',facecolor=fig.get_facecolor());plt.close(fig)
    return 'data:image/png;base64,'+base64.b64encode(b.getvalue()).decode()

def figures(summary,histories,evidence,out):
    figures=[]
    for m in sorted([m for m in summary['masts'] if m['flagged']],key=lambda m:(m['priority']!='red',m['mast_id']))[:12]:
        pair=[]
        for dark in (False,True):
            p=palette(dark);fig,axes=plt.subplots(1,2,figsize=(11,4.8));fig.patch.set_facecolor(p['bg'])
            h=[r for r in histories[m['mast_id']] if r['configuration']==m['configuration'] and r['wind'] is not None and r['core'] is not None]
            axes[0].scatter([r['wind'] for r in h],[r['core'] for r in h],s=9,alpha=.5,color=p['blue']);axes[0].set(xlabel='Forecast wind (m/s)',ylabel='RMS (rad/(m·s))',yscale='log',title=f"{m['route']} {m['mast']} · wind response")
            for e in [e for e in evidence if e['mast_id']==m['mast_id']]:
                with np.load(out/e['filename'],allow_pickle=False) as data:axes[1].loglog(data['frequency'][1:],data['psd'][1:],lw=1,label=date(e['source_epoch']))
            axes[1].set(xlabel='Frequency (Hz)',ylabel='Phase-rate PSD',title='Preserved source spectra')
            if axes[1].lines:axes[1].legend(frameon=False,fontsize=9)
            for ax in axes:frame(ax,p)
            fig.tight_layout();pair.append(uri(fig))
        figures.append({'mast_id':m['mast_id'],'title':f"{m['route']} {m['mast']}",'light':pair[0],'dark':pair[1]})
    return figures

def mast_map(masts):
    if not masts:return ''
    lon=[m['longitude'] for m in masts];lat=[m['latitude'] for m in masts];xmin,xmax=min(lon),max(lon);ymin,ymax=min(lat),max(lat)
    sx=lambda x:30+900*(x-xmin)/(xmax-xmin or 1)
    sy=lambda y:500-470*(y-ymin)/(ymax-ymin or 1)
    parts=['<svg viewBox="0 0 960 530" role="img" aria-label="Geographic mast screening map"><rect width="960" height="530" fill="var(--card)"/>']
    land=Path(__file__).with_name('report_assets')/'land.json'
    for geom in json.loads(land.read_text()):
        polygons=geom['coordinates'] if geom['type']=='MultiPolygon' else [geom['coordinates']]
        for polygon in polygons:
            for ring in polygon:
                parts.append('<polygon fill="var(--bg)" stroke="var(--line)" stroke-width="1" points="'+' '.join(f'{sx(x):.1f},{sy(y):.1f}' for x,y in ring)+'"/>')
    for route in sorted({m['route'] for m in masts}):
        group=[m for m in masts if m['route']==route];parts.append('<polyline fill="none" stroke="var(--dim)" stroke-width="1" points="'+' '.join(f'{sx(m["longitude"]):.1f},{sy(m["latitude"]):.1f}' for m in group)+'"/>')
    colors={'red':'#bf616a','yellow':'#d0a44b','green':'#74a278','grey':'#888'}
    for m in sorted(masts,key=lambda m:m['flagged']):
        c=m['priority'] if m['flagged'] else 'green' if m['eligible'] else 'grey'
        parts.append(f'<circle cx="{sx(m["longitude"]):.1f}" cy="{sy(m["latitude"]):.1f}" r="{5 if m["flagged"] else 2.5}" fill="{colors[c]}"><title>{esc(m["route"])} {esc(m["mast"])}: {c}</title></circle>')
    parts.append('<text x="20" y="522" fill="var(--fg)" font-size="13">N ↑ · Natural Earth coastline; route connections illustrative. Red / yellow: review priority. Green: not flagged. Grey: insufficient evidence.</text></svg>')
    return ''.join(parts)

def render(report_id,summary,observations,ai_status,analysis,figs,out,kind='manual'):
    css=Path(__file__).with_name('report.css').read_text()
    for family,name in [('IBM Plex Sans','sans'),('IBM Plex Sans Condensed','heading'),('IBM Plex Mono','mono')]:
        encoded=base64.b64encode((Path(__file__).with_name('report_assets')/(name+'.woff2')).read_bytes()).decode()
        css+=f'@font-face{{font-family:"{family}";src:url(data:font/woff2;base64,{encoded}) format("woff2");font-weight:{700 if name=="heading" else 400};}}'
    top=f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Power-line integrity · {date(summary["period_end"])}</title><style>{css}</style>'
    body=f'<header class="mast"><div class="kicker">Sensnet · {esc(kind)} report {report_id}</div><h1>Power-line integrity</h1><p class="standfirst">{date(summary["period_start"])} – {date(summary["period_end"])}. Weekly observations in a rolling 30-day context.</p><div class="sourcebar"><span class="src">DAS · explicit channel mapping</span><span class="src">MET / YR forecast context</span><span class="src">Review required</span></div></header>'
    if kind=='historical':body+='<p><a href="/assets/power-line-integrity-20261022.html" target="_blank" rel="noopener">Read the original detailed October report and interactive map</a></p>'
    counts={k:sum(o['assessment']==k for o in observations) for k in ('new','continuing','recurrence','suppressed')}
    body+='<div class="kpis">'+''.join(f'<div class="kpi"><b>{v}</b><span>{esc(k)}</span></div>' for k,v in counts.items())+'</div>'
    body+=f'<p class="note">Usable windows: {summary["usable_windows"]} / {summary["selected_windows"]}; actual data: {date(summary["actual_start"])} – {date(summary["actual_end"])}. Missing/changed files: {summary["missing_windows"]}.</p>'
    body+='<h2><span class="tag">Screening</span>Masts requiring attention</h2>'+mast_map(summary['masts'])
    body+='<p class="note">Wind-related vibration identifies investigation candidates; it does not establish loose masts or structural safety. Closed patterns remain visible in the screening map but are suppressed from new cases unless recurrence criteria are met.</p>'
    body+='<h2><span class="tag">Review queue</span>New findings and follow-up</h2><div class="twrap"><table><tr><th>Finding</th><th>Mast</th><th>Assessment</th><th>Wind correlation</th><th>RMS gain</th><th>Local contrast gain</th></tr>'
    for o in observations:
        m=o['metrics'];body+=f'<tr><td>#{o["finding_id"]}</td><td>{esc(m["route"])} {esc(m["mast"])}</td><td>{esc(o["assessment"])}</td><td>{number(m.get("rho"))}</td><td>{number(m.get("gain"))}</td><td>{number(m.get("contrast_gain"))}</td></tr>'
    body+='</table></div><h2><span class="tag">Interpretation</span>AI analysis</h2>'
    if analysis:
        body+=f'<p>{esc(analysis["summary"])}</p>'
        for f in analysis['findings']:body+=f'<h3>Finding #{f["finding_id"]}</h3><p>{esc(f["interpretation"])}</p><p class="note">Alternatives: {esc(f["alternatives"])}<br>Next check: {esc(f["next_check"])}</p>'
        body+='<p class="note">'+esc(' '.join(analysis['limitations']))+'</p>'
    else:body+=f'<p>AI analysis {esc(ai_status)}. Numerical screening and preserved evidence are available for human review.</p>'
    for f in figs:body+=f'<h2><span class="tag">Evidence</span>{esc(f["title"])}</h2><div class="imgpair"><img class="light" src="{f["light"]}" alt="Wind response and spectra"><img class="dark" src="{f["dark"]}" alt="Wind response and spectra"></div><p class="note">Hourly medians avoid treating adjacent sampled windows as independent observations. Spectra use the preserved raw mast neighbourhood.</p>'
    body+='<h2><span class="tag">Reproduce</span>Method and coverage</h2><pre class="run">python -m src.Mapui.report_worker '+('--weekly' if kind=='weekly' else '')+f'\nReport ID: {report_id}\nUsable source windows: {summary["usable_windows"]}</pre>'
    body+='<p class="note">Calm: wind ≤3 m/s and temperature &gt;2 °C; windy: ≥8 m/s. Each comparison requires eight hourly observations on two dates per group. Wind screening requires Spearman correlation &gt;0.4, RMS gain &gt;1.5 and core/flank contrast gain &gt;1.5. Red additionally requires contrast gain ≥2 and windy core/flank ratio ≥2. Core ±16.5 m; flanks 48–120 m, excluding other mast neighbourhoods. Only compatible configurations are compared.</p>'
    body+='<p class="note">'+esc(' '.join(summary['limitations']))+'</p><p class="note">Provenance: summary.json, sources.json, metrics.npz, hourly.json, evidence-*.npz and ai-input.json are retained beside this immutable report. Evidence checksums and human review history are stored in PostgreSQL.</p></html>'
    (out/'report.html.tmp').write_text(top+body)
    (out/'report.html.tmp').replace(out/'report.html')
