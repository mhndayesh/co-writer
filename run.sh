#!/usr/bin/env bash
# One command to run G-Ink Novel Studio locally.
#
#   ./run.sh
#
# Starts the FastAPI backend on :8080 and the Next.js frontend on :3000.
# Ctrl+C stops both. Logs are streamed to your terminal with [api]/[web] tags.
# If you don't have LM Studio running, the AI just degrades to a fallback
# provider — the UI still works.

set -e

# Always work from the script's own directory regardless of where it was invoked.
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
EOF
fi

if [ ! -f "$WEB_DIR/.env.local" ]; then
  echo "NEXT_PUBLIC_API_BASE_URL=http://localhost:8080" > "$WEB_DIR/.env.local"
fi

# ── 2. Migrate DB (idempotent — alembic skips already-applied) ─────────
( cd "$API_DIR" && "$VENV_ALEMBIC" upgrade head )

# ── 3. Kill anything still on our ports ────────────────────────────────
pkill -f "uvicorn app.main" 2>/dev/null || true
pkill -f "next dev -p 3000" 2>/dev/null || true
sleep 1

# ── 4. Start backend + frontend in background, stream tagged logs ──────
trap 'echo; echo "Stopping..."; kill 0 2>/dev/null; exit 0' INT TERM EXIT

echo "▸ backend  http://localhost:8080"
echo "▸ frontend http://localhost:3000"
echo "▸ Ctrl+C to stop both"
echo

( "$VENV_UVICORN" app.main:app --host 127.0.0.1 --port 8080 --reload \
    --app-dir "$API_DIR" --reload-dir "$API_DIR/app" 2>&1 | sed -u 's/^/[api] /' ) &

( cd "$WEB_DIR" && npm run dev 2>&1 | sed -u 's/^/[web] /' ) &

wait
