#!/usr/bin/env bash
# Writes CSV to stdout; database reads only. Redirect to a NEW local CSV file.
set -euo pipefail
ssh "${1:-inst@10.147.20.10}" "psql -U sensnetdbu -h localhost -d sensnetdb -X -q -v ON_ERROR_STOP=1" <<'SQL'
BEGIN READ ONLY;
COPY (SELECT lid, channel, latitude, longitude, distance, gid FROM public.masteliste ORDER BY lid,channel) TO STDOUT WITH (FORMAT CSV, HEADER TRUE);
COMMIT;
SQL
