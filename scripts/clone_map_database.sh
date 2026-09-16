#!/usr/bin/env bash
# Requires a running isolated cluster and PostgreSQL client tools.
# Creates a NEW local database. Never drops/replaces an existing one.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT_DIR="$PWD"
TARGET_DB="${1:-sensnetdb_local}"
if [[ ! "$TARGET_DB" =~ ^sensnetdb_(local|test)(_[a-z0-9_]+)?$ ]]; then
    echo 'Target must be named sensnetdb_local or sensnetdb_test, optionally suffixed.' >&2
    exit 1
fi
mkdir -p .local
DUMP_PATH="$ROOT_DIR/.local/sensnetdb-$(date +%Y%m%d-%H%M%S).dump"
ssh inst@10.147.20.10 'pg_dump -U sensnetdbu -h localhost -d sensnetdb -Fc --no-owner --no-acl' > "$DUMP_PATH"
createdb -h "$ROOT_DIR/.local/pgsocket" -p 55432 "$TARGET_DB"
pg_restore -h "$ROOT_DIR/.local/pgsocket" -p 55432 -d "$TARGET_DB" --no-owner --no-acl --exit-on-error "$DUMP_PATH"
psql -h "$ROOT_DIR/.local/pgsocket" -p 55432 -d "$TARGET_DB" -X -v ON_ERROR_STOP=1 -f migrations/004_investigation.sql
printf 'Restored %s from %s\n' "$TARGET_DB" "$DUMP_PATH"
