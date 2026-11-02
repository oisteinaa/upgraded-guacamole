"""Versioned screening rules, never structural safety classifications."""
from datetime import datetime,timedelta,timezone
import math

VERSION='weekly-mast-v1'
CLASSES=['Normal Operations','Ice Loading','Wind Galloping','External Interference',
         'Structural / Attachment Anomaly','Sensing / Acquisition Artefact']

def periods(now=None,weekly=False):
    now=now or datetime.now(timezone.utc)
    end=now.astimezone(timezone.utc).replace(minute=0,second=0,microsecond=0)
    if weekly:end=(end-timedelta(days=end.weekday())).replace(hour=0)
    return end-timedelta(days=7),end,end-timedelta(days=30)

def classify(m):
    if not m.get('eligible'):return 'grey'
    if m.get('rho',0)>.4 and m.get('gain',0)>1.5 and m.get('contrast_gain',0)>1.5:
        return 'red' if m['contrast_gain']>=2 and m.get('wind_contrast',0)>=2 else 'yellow'
    return 'green'

def recurrence(closed,current):
    """No comparisons across configurations, or using evidence preceding closure."""
    if not current.get('post_closure_qualified'):return False
    if closed.get('configuration')!=current.get('configuration'):return False
    if current.get('closure_reason')=='repaired':return bool(current.get('flagged'))
    # Match the same weather bins, requiring adequate days/hours in each period.
    ratios=[]
    for key,now in current.get('weather_bins',{}).items():
        before=closed.get('weather_bins',{}).get(key)
        if not before or min(now.get('hours',0),before.get('hours',0))<8:continue
        if min(now.get('days',0),before.get('days',0))<2:continue
        if before.get('contrast',0)>0:ratios.append(now['contrast']/before['contrast'])
    return bool(ratios and max(ratios)>=2)

def finite_json(value):
    if isinstance(value,dict):return {str(k):finite_json(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [finite_json(v) for v in value]
    if hasattr(value,'item'):return finite_json(value.item())
    if isinstance(value,float) and not math.isfinite(value):return None
    if isinstance(value,datetime):return value.isoformat()
    return value
