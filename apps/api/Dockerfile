FROM python:3.12-slim AS base
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
 && rm -rf /var/lib/apt/lists/*

FROM base AS deps
COPY pyproject.toml ./
# Include the [stripe] extra so BILLING_PROVIDER=stripe works in the prod image
# (the SDK is imported lazily, so it's harmless when billing is manual).
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -e .[stripe]

FROM python:3.12-slim AS runner
WORKDIR /app
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --no-create-home --shell /bin/false gink
COPY . .
# COPY preserves host file modes — a stray non-world-readable file would crash the
# non-root user at import. Force read/traverse for all, then mark the entrypoint exec.
RUN chmod -R a+rX /app && chmod +x entrypoint.sh
USER gink
EXPOSE 8080
# Migrations run separately (see entrypoint.sh comment). Never run alembic inside
# the long-running container CMD — it races when api replicas > 1.
CMD ["./entrypoint.sh"]
