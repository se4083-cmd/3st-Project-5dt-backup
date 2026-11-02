#!/usr/bin/env sh
set -eu
# App Service built-in Linux Python runtime; configure this file as Startup Command.
# Migration and seed deliberately do not run in API worker processes.
exec python -m uvicorn app.main:create_app --factory \
  --host 0.0.0.0 --port "${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-2}" \
  --proxy-headers --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}" \
  --no-access-log --log-level info
