import json

import pytest
from fastapi import HTTPException

from src.Mapui import api


def fixture_source(tmp_path, monkeypatch):
    monkeypatch.setenv('DAS_ARCHIVE_ROOT', str(tmp_path))
    ref = dict(path=str(tmp_path / 'sample.hdf5'), stamp=[100, 200], start_sample=10, stop_sample=90)
    row = dict(window_id='abc', start_epoch='1000.1', duration_seconds='0.8', channel_start='1', channel_stop='3', channel_ids='[4, 8]', refs=json.dumps([ref]))
    ctx = dict(recording_id=1, start_sample=10, stop_sample=90, alignment_verified=False,
               evidence='discovery-window:abc\nUnverified alignment\n' + json.dumps(row))
    rec = dict(relative_path='sample.hdf5', size_bytes=100, mtime_ns=200,
               channels=[0, 4, 8, 12], samples=100, dt=.01, acquisition_epoch=1000,
               time_verified=False, mapping_verified=False, lid=None)
    return ctx, rec


def test_source_link_does_not_require_clock_or_geography(tmp_path, monkeypatch):
    ctx, rec = fixture_source(tmp_path, monkeypatch)
    assert api.discovery_source(ctx, rec) == [4, 8]
    ctx['source_linked'] = True
    monkeypatch.setattr(api, 'event_detail', lambda _: dict(context=ctx))
    monkeypatch.setattr(api, 'get_recording', lambda _: rec)
    calls = []
    monkeypatch.setattr(api, 'read_stitched_signal', lambda *a, **kw: calls.append((a, kw)) or {})
    result = api.event_signal(1, 0, 0, 100)
    assert calls[0][0][1:4] == pytest.approx((8, .1, .8))
    assert calls[0][1]['channel_bounds'] == [4, 8]
    assert result['event_end'] == pytest.approx(.9)
    assert 'unverified' in result['source_note']
    assert not rec['time_verified'] and not ctx['alignment_verified']


@pytest.mark.parametrize('change', ['stamp', 'channels', 'samples', 'marker'])
def test_invalid_source_is_rejected(tmp_path, monkeypatch, change):
    ctx, rec = fixture_source(tmp_path, monkeypatch)
    if change == 'stamp': rec['mtime_ns'] = 201
    if change == 'channels': rec['channels'] = [0, 5, 9, 12]
    if change == 'samples': ctx['stop_sample'] = 91
    if change == 'marker': ctx['evidence'] = 'Legacy comment'
    assert api.discovery_source(ctx, rec) is None


def test_legacy_without_reference_stays_unlinked(monkeypatch):
    monkeypatch.setattr(api, 'event_detail', lambda _: dict(context=None))
    with pytest.raises(HTTPException) as error:
        api.event_signal(1, 0, 0, 100)
    assert error.value.status_code == 404
