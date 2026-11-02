"""Bounded, UTC archive browsing without reading HDF5 channel arrays."""
from datetime import datetime, timedelta, timezone

from .db import rows
from .signals import safe_path

FIELDS = """id,relative_path,acquisition_epoch,dt,samples,unit,lid,
    time_verified,mapping_verified,processing,
    cardinality(channels) AS channel_count,channels[1] AS first_channel"""


def availability(items):
    for item in items:
        try:
            safe_path(item['relative_path'])
            item['available'] = True
        except (ValueError, OSError):
            item['available'] = False
    return items


def browse(day=None, hour=None, offset=0, limit=200):
    days = rows("""SELECT to_char(to_timestamp(acquisition_epoch) AT TIME ZONE 'UTC', 'YYYY-MM-DD') AS day,
        count(*) AS count FROM das_recordings GROUP BY 1 ORDER BY 1 DESC""")
    latest = availability(rows(f"SELECT {FIELDS} FROM das_recordings ORDER BY acquisition_epoch DESC,id DESC LIMIT 1"))
    if day is None:
        day = days[0]['day'] if days else None
    if day is None:
        return dict(days=[], day=None, hours=[], hour=None, items=[], total=0, offset=0, limit=limit, latest=None)
    start = datetime.strptime(day, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    lo, hi = start.timestamp(), (start + timedelta(days=1)).timestamp()
    hours = rows("""SELECT floor((acquisition_epoch-%s)/3600)::integer AS hour,count(*) AS count
        FROM das_recordings WHERE acquisition_epoch >= %s AND acquisition_epoch < %s
        GROUP BY 1 ORDER BY 1 DESC""", (lo, lo, hi))
    if hour is None:
        hour = hours[0]['hour'] if hours else 0
    total = next((r['count'] for r in hours if r['hour'] == hour), 0)
    offset = min(offset, max(0, (total-1)//limit)*limit)
    begin = lo + hour * 3600
    items = availability(rows(f"""SELECT {FIELDS} FROM das_recordings
        WHERE acquisition_epoch >= %s AND acquisition_epoch < %s
        ORDER BY acquisition_epoch DESC,id DESC LIMIT %s OFFSET %s""", (begin, begin+3600, limit, offset)))
    return dict(days=days, day=day, hours=hours, hour=hour, items=items,
                total=total, offset=offset, limit=limit, latest=latest[0] if latest else None)
