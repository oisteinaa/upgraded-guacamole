#!/usr/bin/env bash
# Independent of the legacy application, virtualenv and capture processes.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT_DIR="$PWD"
if [[ -f .local/map-server.env ]]; then
    set -a
    source .local/map-server.env
    set +a
fi
export DAS_DATABASE_URL="${DAS_DATABASE_URL:-dbname=sensnetdb user=sensnetdbu host=localhost}"
export DAS_ARCHIVE_ROOT="${DAS_ARCHIVE_ROOT:-/home/inst/DataCopy}"
export DAS_ENVIRONMENT="${DAS_ENVIRONMENT:-Server investigation}"
export DAS_LIVE_SNAPSHOT="${DAS_LIVE_SNAPSHOT:-$ROOT_DIR/.local/server-live.json}"
export DAS_METRIC_CACHE="${DAS_METRIC_CACHE:-$ROOT_DIR/.local/metric-cache}"
export DAS_REVIEW_WRITES="${DAS_REVIEW_WRITES:-0}"
export DAS_BIND_HOST="${DAS_BIND_HOST:-0.0.0.0}"
PYTHON="$ROOT_DIR/.venv-map/bin/python"
[[ -x "$PYTHON" ]] || { echo 'Install requirements-map.txt into .venv-map first.' >&2; exit 1; }
[[ -f web/dist/index.html ]] || { echo 'Build the frontend: cd web && npm ci && npm run build' >&2; exit 1; }
"$PYTHON" - <<'PY'
from src.Mapui.db import database
with database() as cur:
    for table in ('das_recordings', 'event_context', 'event_reviews'):
        cur.execute('SELECT to_regclass(%s)', ('public.' + table,))
        if cur.fetchone()['to_regclass'] is None:
            raise SystemExit('Missing ' + table + ': migration 004_investigation.sql must be approved and applied first.')
PY
exec "$PYTHON" -m src.Mapui.launcher "$@"
