#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
set -a
[[ ! -f .local/map-server.env ]] || source .local/map-server.env
[[ ! -f .local/report-ai.env ]] || source .local/report-ai.env
set +a
export DAS_DATABASE_URL="${DAS_DATABASE_URL:-dbname=sensnetdb user=sensnetdbu host=localhost}"
export DAS_ARCHIVE_ROOT="${DAS_ARCHIVE_ROOT:-/home/inst/DataCopy}"
export DAS_EXISTING_METRIC_CACHE="${DAS_METRIC_CACHE:-$PWD/.local/metric-cache}"
export DAS_METRIC_CACHE="$PWD/.local/report-metric-cache"
export MPLCONFIGDIR="$PWD/.local/report-matplotlib"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
exec .venv-reports/bin/python -m src.Mapui.report_worker "$@"
