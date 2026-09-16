#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export WEATHER_DATABASE_URL="dbname=sensnetdb_local host=$PWD/.local/pgsocket port=55432"
exec .venv-map/bin/python src/weather/weather_capture.py --cache-dir "$PWD/.local/weather-cache"
