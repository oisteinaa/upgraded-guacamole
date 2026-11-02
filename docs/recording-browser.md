# Recording browser

Signal investigation browses all indexed acquisition days, grouped by UTC day
and hour. The file list shows acquisition time, filename and duration, newest
first. Each page holds up to 200 files; Newer and Older browse the remaining
files in that hour. Files no longer present in the configured archive are
marked unavailable and cannot be selected.

The list refreshes every 15 seconds and when the window regains focus. Refresh
updates it immediately. These updates retain the selected file and signal
window; Latest file returns to the newest day/hour and selects its newest
available file. Choosing a different day or hour selects its newest available
file. Changing pages retains the selected recording until another is chosen.
Switching recordings (including day/hour selection, Latest file and playback)
preserves channel ID, channel count, mast span, start and duration. The new file
loads with those controls, including pending time-window edits. Explicit frame
navigation within a file and Reset signal window still change the time window.

The browser reads `das_recordings`, populated by the existing live capture
indexer; it does not scan storage or insert database rows. New recordings appear
after indexing. Older days appear if they have indexed files, although retention
may have removed their source data. Browser dates use acquisition UTC, independent
of the database session timezone.

`GET /api/recording-browser` accepts `day=YYYY-MM-DD`, `hour=0..23`, `offset`
and `limit=1..500` (default 200). Omitted day/hour select the latest indexed
day/hour. Responses include day/hour counts, bounded file metadata, availability,
and the latest indexed recording. `GET /api/recordings/{id}` resolves metadata
for a selected recording outside the current page. Both return `Cache-Control:
no-store`; neither endpoint reads signal arrays. The legacy `/api/recordings`
endpoint remains available for existing clients.

Checks: `tests/test_recording_browser.py` covers UTC boundaries, pagination,
availability, fresh queries and API validation. Browser validation and deployment
evidence are in `results/recording-browser-20261015/`.
