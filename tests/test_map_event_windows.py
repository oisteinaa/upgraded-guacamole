from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.Mapui import api


def test_latest_day_uses_stored_recording_day():
    assert api.map_event_window('latest_day',None,None,latest=datetime(2026,6,16,2,14)) == (datetime(2026,6,16),datetime(2026,6,17))


def test_rolling_window_uses_elapsed_time_across_dst():
    now=datetime(2026,10,25,12,tzinfo=ZoneInfo('Europe/Oslo'))
    assert api.map_event_window('day',None,None,now=now) == (datetime(2026,10,24,13),datetime(2026,10,25,12))


def test_custom_needs_both_bounds():
    with pytest.raises(HTTPException):
        api.map_event_window('custom',datetime(2026,6,16),None)


def test_map_filters_applied_before_limit(monkeypatch):
    queries=[]
    def rows(sql,args=()):
        queries.append((sql,args))
        if 'max(time)' in sql:return [{'latest':datetime(2026,6,16,2)}]
        return []
    monkeypatch.setattr(api,'rows',rows)
    client=TestClient(api.app)
    response=client.get('/api/map/events?window=latest_day&classes=0,4&review=unreviewed')
    assert response.status_code==200
    assert response.json()['window_start']=='2026-06-16T00:00:00'
    for sql,args in queries[1:]:
        assert 'COALESCE(e.classid,0)=ANY(%s)' in sql
        assert 'NOT EXISTS' in sql
        assert args==[datetime(2026,6,16),datetime(2026,6,17),[0,4]]
    assert client.get('/api/map/events?classes=bad').status_code==422
    assert client.get('/api/map/events?window=custom&start=2026-06-17&end=2026-06-16').status_code==422
    response=client.get('/api/map/events?classes=')
    assert response.status_code==200 and queries[-1][1][-1]==[]
