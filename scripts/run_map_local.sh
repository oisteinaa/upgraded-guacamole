#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT_DIR="$PWD"
PG_BIN="${DAS_PG_BIN:-$ROOT_DIR/.local/runtime/pg/usr/lib/postgresql/15/bin}"
export DAS_DATABASE_URL="dbname=sensnetdb_local host=$ROOT_DIR/.local/pgsocket port=55432"
export DAS_ARCHIVE_ROOT="$ROOT_DIR/.local/recordings"
export DAS_ENVIRONMENT='Local investigation'
export DAS_LIVE_SNAPSHOT="$ROOT_DIR/.local/live.json"
if ! "$PG_BIN/pg_ctl" -D "$ROOT_DIR/.local/pgdata" status >/dev/null 2>&1; then
    "$PG_BIN/pg_ctl" -D "$ROOT_DIR/.local/pgdata" -l "$ROOT_DIR/.local/postgres.log" \
        -o "-k $ROOT_DIR/.local/pgsocket -p 55432 -c listen_addresses=''" start
fi
exec "$ROOT_DIR/.venv-map/bin/python" -m uvicorn src.Mapui.api:app --host 127.0.0.1 --port 8051
