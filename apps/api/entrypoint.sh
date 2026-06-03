#!/bin/sh
# Container entrypoint for the API service.
#
# Migrations are NOT run here; run them once via:
#   docker compose run --rm api alembic upgrade head
# or the CI deploy step. Running them inside the long-running container CMD
# causes a race when api replicas > 1 (concurrent alembic upgrade races).
set -e
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8080 \
  --workers 2 \
  --proxy-headers \
  --forwarded-allow-ips='*'
