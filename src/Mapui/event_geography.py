"""Locate source channel blocks against the current fibre and mast inventory."""
from .db import rows
from .metrics import fibre_positions, geographic_distance, interpolation_regions, resolve_positions
from .signals import safe_path


def locate_source(recording, channels, cache=None):
    cache = {} if cache is None else cache
    stat = safe_path(recording['relative_path']).stat()
    if (stat.st_size, stat.st_mtime_ns) != (recording['size_bytes'], recording['mtime_ns']):
        raise ValueError('Recording changed; re-index before locating')
    lid = recording['lid']
    basis = 'Recording instrument ID'
    if lid is None:
        if 'lids' not in cache:
            cache['lids'] = [r['lid'] for r in rows('SELECT DISTINCT lid FROM masteliste ORDER BY lid')]
        if len(cache['lids']) != 1:
            return None
        lid = cache['lids'][0]
        basis = 'Only configured DAS line; header ROI origin checked against current fibre mapping'
    if ('positions', lid) not in cache:
        cache['positions', lid] = fibre_positions(lid)
    positions = cache['positions', lid]
    regions = interpolation_regions(recording, positions)
    # Even exact IDs need shared-axis evidence when the recording has no instrument ID.
    if recording['lid'] is None and not all(any(r['start'] <= c <= r['end'] for r in regions) for c in channels):
        return None
    mapped, counts = resolve_positions(dict(recording, channels=channels), positions, regions)
    if not mapped:
        return None
    center = channels[len(channels) // 2]
    representative = min(mapped, key=lambda p: abs(p['recording_channel'] - center))
    if ('masts', lid) not in cache:
        cache['masts', lid] = rows('SELECT id,route,mast,channel,lid,latitude,longitude,channel_distance_m FROM masts WHERE lid=%s', (lid,))
        cache['spans', lid] = rows('''SELECT span_id,route,from_mast,to_mast,from_channel,to_channel,
            from_mast_id,to_mast_id,connection_status,review_reason FROM v_mast_spans
            WHERE from_lid=%s AND to_lid=%s ORDER BY route,span_order''', (lid,lid))
    spans = [s for s in cache['spans', lid] if any(
        min(s['from_channel'], s['to_channel']) <= p['recording_channel'] <= max(s['from_channel'], s['to_channel']) for p in mapped)]
    nearest = sorted((dict(m, distance_m=geographic_distance(representative, m))
                      for m in cache['masts', lid]), key=lambda m: m['distance_m'])[:2]
    return dict(lid=lid, channel=representative['recording_channel'],
                channel_start=min(channels), channel_end=max(channels),
                latitude=representative['latitude'], longitude=representative['longitude'],
                mapping=representative['mapping'], lower_channel=representative['lower_channel'],
                upper_channel=representative['upper_channel'], mapping_counts=counts,
                located_channels=len(mapped), total_channels=len(channels),
                basis=basis, spans=spans, nearest_masts=nearest,
                routes=sorted({s['route'] for s in spans}),
                note='Current channel mapping; marker represents the sampled block, not a pinpointed incident. Spans are inferred inventory connections; recording time remains unverified.')
