from pathlib import Path
from types import SimpleNamespace

import pytest

from src.Mapui import event_geography as geo


@pytest.fixture
def source(monkeypatch):
    rec = dict(relative_path='x', size_bytes=100, mtime_ns=200, lid=None, channels=[100,104,108])
    monkeypatch.setattr(geo, 'safe_path', lambda _: SimpleNamespace(stat=lambda: SimpleNamespace(st_size=100,st_mtime_ns=200)))
    positions = [dict(channel=c,lid=1,latitude=68,longitude=14+(c-100)*.00001,gid=1,distance=c,run='1:100') for c in [99,103,107,111]]
    monkeypatch.setattr(geo, 'fibre_positions', lambda _: positions)
    monkeypatch.setattr(geo, 'interpolation_regions', lambda *a: [dict(start=99,end=111,step=4,native_spacing_m=1)])
    def rows(sql, args=()):
        if 'DISTINCT' in sql: return [dict(lid=1)]
        if 'FROM masts ' in sql: return [dict(id=1,route='R06',mast='M1',channel=99,lid=1,latitude=68,longitude=14,channel_distance_m=0)]
        return [dict(span_id=1,route='R06',from_mast='M1',to_mast='M2',from_channel=99,to_channel=105)]
    monkeypatch.setattr(geo, 'rows', rows)
    return rec


def test_interpolated_location_and_span_without_verified_time(source):
    result=geo.locate_source(source, source['channels'])
    assert result['channel']==104 and result['mapping']=='interpolated'
    assert (result['lower_channel'],result['upper_channel'])==(103,107)
    assert result['routes']==['R06'] and result['spans'][0]['from_mast']=='M1'
    assert result['nearest_masts'][0]['mast']=='M1'
    assert result['located_channels']==3
    assert 'unverified' in result['note']


def test_mapped_channel_without_span_still_has_coordinates(source,monkeypatch):
    original=geo.rows
    monkeypatch.setattr(geo,'rows',lambda sql,args=(): [] if 'v_mast_spans' in sql else original(sql,args))
    result=geo.locate_source(source,source['channels'])
    assert result['spans']==[] and result['routes']==[]
    assert result['latitude']==68 and result['nearest_masts']


def test_ambiguous_line_not_guessed(source,monkeypatch):
    monkeypatch.setattr(geo,'rows',lambda *a:[dict(lid=1),dict(lid=2)])
    assert geo.locate_source(source,source['channels']) is None


def test_missing_axis_evidence_not_guessed(source,monkeypatch):
    monkeypatch.setattr(geo,'interpolation_regions',lambda *a:[])
    assert geo.locate_source(source,source['channels']) is None


def test_changed_file_rejected(source):
    source['mtime_ns']=201
    with pytest.raises(ValueError,match='changed'):
        geo.locate_source(source,source['channels'])
