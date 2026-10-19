#!/usr/bin/env bash
# Start Job OS at http://localhost:8000
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi
[ -f .env ] && set -a && . ./.env && set +a
(sleep 1.5 && open http://localhost:8000) >/dev/null 2>&1 &
exec .venv/bin/uvicorn app.main:app --port 8000 --reload --reload-dir app
