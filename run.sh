#!/usr/bin/env bash
# One command to run G-Ink Novel Studio locally.
#
#   ./run.sh
#
# Starts Qdrant + Neo4j (Docker), the FastAPI backend on :8080, and the
# Next.js frontend on :3000.  Ctrl+C stops everything.
# Logs are streamed with [api]/[web] tags.
# If you don't have LM Studio running, the AI degrades to a fallback
# provider — the UI still works.

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

API_DIR="$ROOT/apps/api"
WEB_DIR="$ROOT/apps/web"
VENV_PY="$API_DIR/.venv/bin/python"
VENV_UVICORN="$API_DIR/.venv/bin/uvicorn"
VENV_ALEMBIC="$API_DIR/.venv/bin/alembic"

# ── 0. Sanity checks ───────────────────────────────────────────────────
if [ ! -x "$VENV_UVICORN" ]; then
  echo "ERROR: $VENV_UVICORN not found."
  echo "First-time setup:"
  echo "  cd '$API_DIR' && python3 -m venv .venv && ./.venv/bin/pip install -e .[dev]"
  exit 1
fi
if [ ! -x "$VENV_ALEMBIC" ]; then
  echo "ERROR: $VENV_ALEMBIC not found — venv exists but deps not installed."
  echo "Install with:"
  echo "  '$API_DIR/.venv/bin/pip' install -e '$API_DIR'[dev]"
  exit 1
fi

if [ ! -d "$WEB_DIR/node_modules" ]; then
  echo "Installing frontend deps (first run only)..."
  ( cd "$WEB_DIR" && npm install --legacy-peer-deps )
fi

# ── 1. .env (auto-generated on first run) ──────────────────────────────
if [ ! -f "$API_DIR/.env" ]; then
  echo "Generating $API_DIR/.env with fresh secrets..."
  JWT=$("$VENV_PY" -c "import secrets; print(secrets.token_urlsafe(64))")
  FERNET=$("$VENV_PY" -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
  cat > "$API_DIR/.env" <<EOF
DATABASE_URL=sqlite+aiosqlite:///$(pwd)/$API_DIR/gink_dev.db
JWT_SECRET=$JWT
LLM_KEY_ENCRYPTION_KEY=$FERNET
LLM_PROVIDER=lmstudio
LMSTUDIO_BASE_URL=http://localhost:1234/v1
CORS_ORIGINS=http://localhost:3000
QDRANT_URL=http://localhost:6333
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=gink_dev_password
EOF
fi

# Append any missing service URLs to an existing .env (idempotent)
grep -q '^QDRANT_URL=' "$API_DIR/.env"   || echo "QDRANT_URL=http://localhost:6333"      >> "$API_DIR/.env"
grep -q '^NEO4J_URI=' "$API_DIR/.env"    || echo "NEO4J_URI=bolt://localhost:7687"        >> "$API_DIR/.env"
grep -q '^NEO4J_USER=' "$API_DIR/.env"   || echo "NEO4J_USER=neo4j"                       >> "$API_DIR/.env"
grep -q '^NEO4J_PASSWORD=' "$API_DIR/.env" || echo "NEO4J_PASSWORD=gink_dev_password"     >> "$API_DIR/.env"

if [ ! -f "$WEB_DIR/.env.local" ]; then
  echo "NEXT_PUBLIC_API_BASE_URL=http://localhost:8080" > "$WEB_DIR/.env.local"
fi

# ── 2. Optional services via Docker ────────────────────────────────────
DOCKER_OK=false
if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
  DOCKER_OK=true
fi

start_container() {
  local name="$1"; shift
  local label="$1"; shift
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${name}$"; then
    echo "▸ $label   already running"
    return 0
  fi
  if docker run -d --rm --name "$name" "$@" >/dev/null 2>&1; then
    echo "▸ $label   started"
  else
    echo "  $label start failed (check docker logs $name)"
  fi
}

if $DOCKER_OK; then
  start_container gink-qdrant "qdrant  http://localhost:6333" \
    -p 6333:6333 -p 6334:6334 \
    qdrant/qdrant:latest

  start_container gink-neo4j  "neo4j   http://localhost:7474" \
    -p 7474:7474 -p 7687:7687 \
    -e NEO4J_AUTH=neo4j/gink_dev_password \
    neo4j:5-community
else
  echo "  Docker not available — skipping Qdrant & Neo4j (RAG and graph will be disabled)"
fi

# ── 3. Migrate DB (idempotent) ─────────────────────────────────────────
( cd "$API_DIR" && "$VENV_ALEMBIC" upgrade head )

# ── 4. Kill anything still on our ports ────────────────────────────────
pkill -f "uvicorn app.main" 2>/dev/null || true
pkill -f "next dev -p 3000" 2>/dev/null || true
sleep 1

# ── 5. Start backend + frontend, stream tagged logs ────────────────────
stop_all() {
  echo
  echo "Stopping..."
  if $DOCKER_OK; then
    docker stop gink-qdrant gink-neo4j 2>/dev/null || true
  fi
  kill 0 2>/dev/null
  exit 0
}
trap stop_all INT TERM EXIT

echo
echo "▸ backend  http://localhost:8080"
echo "▸ frontend http://localhost:3000"
echo "▸ Ctrl+C to stop everything"
echo

( "$VENV_UVICORN" app.main:app --host 127.0.0.1 --port 8080 --reload \
    --app-dir "$API_DIR" --reload-dir "$API_DIR/app" 2>&1 | sed -u 's/^/[api] /' ) &

( cd "$WEB_DIR" && npm run dev 2>&1 | sed -u 's/^/[web] /' ) &

wait
