from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.Mapui import recording_browser as browser
from src.Mapui import api


@pytest.mark.parametrize('day', ['2026-03-29', '2026-10-25'])
def test_browser_uses_utc_days_and_bounded_hour_pages(monkeypatch, tmp_path, day):
    monkeypatch.setenv('DAS_ARCHIVE_ROOT', str(tmp_path))
    (tmp_path / 'present.hdf5').touch()
    calls = []
    def rows(sql, params=()):
        calls.append((sql, params))
        if 'to_char' in sql:
            return [dict(day=day, count=800)]
        if 'LIMIT 1' in sql:
            return [dict(id=9, relative_path='present.hdf5')]
        if 'floor' in sql:
            return [dict(hour=23, count=600), dict(hour=0, count=200)]
        return [dict(id=7, relative_path='present.hdf5'), dict(id=6, relative_path='removed.hdf5')]
    monkeypatch.setattr(browser, 'rows', rows)
    result = browser.browse(day, 23, 400, 200)
    epoch = datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp()
    assert calls[2][1] == (epoch, epoch, epoch + 86400)
    assert calls[3][1] == (epoch+23*3600, epoch+86400, 200, 400)
    assert 'ORDER BY acquisition_epoch DESC,id DESC' in calls[3][0]
    assert result['items'][0]['available'] is True
    assert result['items'][1]['available'] is False
    assert result['total'] == 600 and result['offset'] == 400


def test_empty_archive_is_explicit(monkeypatch):
    monkeypatch.setattr(browser, 'rows', lambda *args: [])
    result = browser.browse()
    assert result['days'] == [] and result['items'] == [] and result['latest'] is None


def test_defaults_to_latest_day_hour_and_clamps_removed_page(monkeypatch):
    def rows(sql, params=()):
        if 'to_char' in sql: return [dict(day='2026-10-15', count=361)]
        if 'LIMIT 1' in sql: return []
        if 'floor' in sql: return [dict(hour=10, count=361)]
        assert params[-2:] == (200, 200)
        return []
    monkeypatch.setattr(browser, 'rows', rows)
    result = browser.browse(offset=10000)
    assert (result['day'], result['hour'], result['offset']) == ('2026-10-15', 10, 200)


@pytest.mark.parametrize('query', ['day=bad', 'day=2026-02-30', 'hour=-1', 'hour=24', 'limit=501', 'limit=0', 'offset=-1'])
def test_invalid_browser_requests_never_query_database(monkeypatch, query):
    monkeypatch.setattr(browser, 'rows', lambda *args: pytest.fail('Invalid request reached database'))
    with TestClient(api.app) as client:
        assert client.get('/api/recording-browser?' + query).status_code == 422


def test_metadata_can_fetch_selected_file_outside_current_page(monkeypatch, tmp_path):
    monkeypatch.setenv('DAS_ARCHIVE_ROOT', str(tmp_path))
    (tmp_path/'selected.hdf5').touch()
    def rows(sql, params):
        assert params == (123,)
        return [dict(id=123, relative_path='selected.hdf5')]
    monkeypatch.setattr(api, 'rows', rows)
    with TestClient(api.app) as client:
        response = client.get('/api/recordings/123')
        assert response.status_code == 200
        assert response.json()['available'] is True
        assert response.headers['cache-control'] == 'no-store'


def test_browser_requeries_new_files_and_is_not_cached(monkeypatch):
    calls = []
    def browse(*args):
        calls.append(args)
        return dict(items=[dict(id=len(calls))])
    monkeypatch.setattr(browser, 'browse', browse)
    with TestClient(api.app) as client:
        a = client.get('/api/recording-browser')
        b = client.get('/api/recording-browser')
        assert a.json() != b.json()
        assert a.headers['cache-control'] == 'no-store'
