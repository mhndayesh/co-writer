# Root Dockerfile for the API — builds from the REPO ROOT context so Railway (and
# anything that builds from the repo root) works with NO "Root Directory" setting.
# Same build as apps/api/Dockerfile, just with apps/api/ paths.
FROM python:3.12-slim AS base
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
 && rm -rf /var/lib/apt/lists/*

FROM base AS deps
COPY apps/api/pyproject.toml ./
# [stripe] extra so BILLING_PROVIDER=stripe works (imported lazily; harmless otherwise).
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -e .[stripe]

FROM python:3.12-slim AS runner
WORKDIR /app
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --no-create-home --shell /bin/false gink
COPY apps/api/ ./
# COPY preserves host file modes — force readable so a stray non-world-readable
# file can't crash the non-root user at import. Also pre-create the uploads dir
# owned by the runtime user (cover-image storage); on Railway mount a Volume here.
RUN chmod -R a+rX /app && chmod +x entrypoint.sh \
 && mkdir -p /app/uploads && chown gink:gink /app/uploads
USER gink
EXPOSE 8080
# Binds $PORT (Railway) with an 8080 fallback. Migrations run via railway.json's
# preDeployCommand (or `docker compose run --rm api alembic upgrade head`).
CMD ["./entrypoint.sh"]
