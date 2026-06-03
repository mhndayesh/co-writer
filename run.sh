#!/usr/bin/env bash
# G-Ink Co-Writer — one-command local runner.
#
#   ./run.sh            start everything (foreground, Ctrl+C stops api+web)
#   ./run.sh start      start everything DETACHED (survives terminal close)
#   ./run.sh stop       stop api + web (leaves Qdrant/Neo4j containers up)
#   ./run.sh restart    stop then start (detached)
#   ./run.sh status     show what's running + health
#   ./run.sh logs       tail the api + web logs (detached mode)
#
# First run also: creates .venv, installs deps, generates secrets, runs migrations.
#
# Design notes (why it's shaped this way): the previous version used `set -e` +
# `kill 0` + a foreground `wait`, so ANY flaky external binary (lsof/docker) or a
# stray terminal signal could take the whole script down ("Segmentation fault").
# This version never uses `set -e`, guards every external call, and can run the
# servers fully detached so the launcher exiting never kills them.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT" || exit 1

API_DIR="$ROOT/apps/api"
WEB_DIR="$ROOT/apps/web"
VENV="$API_DIR/.venv"
VENV_PY="$VENV/bin/python"
VENV_PIP="$VENV/bin/pip"
VENV_UVICORN="$VENV/bin/uvicorn"
VENV_ALEMBIC="$VENV/bin/alembic"

LOG_DIR="$ROOT/.run-logs"
API_LOG="$LOG_DIR/api.log"
WEB_LOG="$LOG_DIR/web.log"
API_PIDF="$LOG_DIR/api.pid"
WEB_PIDF="$LOG_DIR/web.pid"
mkdir -p "$LOG_DIR"

GRN='\033[0;32m'; YEL='\033[0;33m'; CYN='\033[0;36m'; RED='\033[0;31m'; RST='\033[0m'
ok()  { echo -e "${GRN}✔${RST} $*"; }
inf() { echo -e "${CYN}▸${RST} $*"; }
wrn() { echo -e "${YEL}⚠${RST}  $*"; }
err() { echo -e "${RED}✖${RST} $*" >&2; }

# ── helpers ────────────────────────────────────────────────────────────────────

# Free a TCP port. Tries lsof, then fuser, then ss — each guarded so a missing or
# crashing tool never aborts the script.
kill_port() {
  local port="$1" pids=""
  if command -v lsof >/dev/null 2>&1; then
    pids=$(lsof -ti:"$port" 2>/dev/null)
  fi
  if [ -z "$pids" ] && command -v fuser >/dev/null 2>&1; then
    pids=$(fuser "$port"/tcp 2>/dev/null)
  fi
  if [ -n "$pids" ]; then
    echo "$pids" | xargs -r kill -9 2>/dev/null
    inf "freed port $port"
  fi
}

port_up() { ss -ltn 2>/dev/null | grep -q ":$1[[:space:]]"; }

wait_for_port() {  # port, label, seconds
  local port="$1" label="$2" max="${3:-40}" i=0
  while [ "$i" -lt "$max" ]; do
    if port_up "$port"; then ok "$label up on :$port"; return 0; fi
    sleep 1; i=$((i + 1))
  done
  wrn "$label did not come up on :$port within ${max}s — check $LOG_DIR"
  return 1
}

is_running() {  # pidfile
  local f="$1"
  [ -f "$f" ] && kill -0 "$(cat "$f" 2>/dev/null)" 2>/dev/null
}

# ── setup (idempotent; only does work on first run) ────────────────────────────

CLERK_JWKS_URL_DEV="https://national-shrew-41.clerk.accounts.dev/.well-known/jwks.json"
CLERK_ISSUER_DEV="https://national-shrew-41.clerk.accounts.dev"
CLERK_PK_DEV="pk_test_bmF0aW9uYWwtc2hyZXctNDEuY2xlcmsuYWNjb3VudHMuZGV2JA"

setup() {
  # Python venv
  if [ ! -x "$VENV_UVICORN" ]; then
    inf "Setting up Python virtualenv (first run — ~60s)..."
    python3.11 -m venv "$VENV" 2>/dev/null || python3 -m venv "$VENV" || { err "python3.11/python3 not found"; exit 1; }
    "$VENV_PIP" install --quiet --upgrade pip
    "$VENV_PIP" install --quiet -e "$API_DIR[dev]" || { err "pip install failed"; exit 1; }
    ok "Python venv ready"
  fi

  # Frontend deps
  if [ ! -d "$WEB_DIR/node_modules" ]; then
    inf "Installing frontend deps (first run — ~30s)..."
    ( cd "$WEB_DIR" && npm install --legacy-peer-deps --silent ) || { err "npm install failed"; exit 1; }
    ok "Node deps ready"
  fi

  # Backend .env
  if [ ! -f "$API_DIR/.env" ]; then
    inf "Generating $API_DIR/.env with fresh secrets..."
    local JWT FERNET
    JWT=$("$VENV_PY" -c "import secrets; print(secrets.token_urlsafe(64))")
    FERNET=$("$VENV_PY" -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    cat > "$API_DIR/.env" <<EOF
DATABASE_URL=sqlite+aiosqlite:///$API_DIR/gink_dev.db
JWT_SECRET=$JWT
LLM_KEY_ENCRYPTION_KEY=$FERNET
LLM_PROVIDER=lmstudio
LMSTUDIO_BASE_URL=http://localhost:1234/v1
LMSTUDIO_MODEL=local-model
LMSTUDIO_EMBED_MODEL=nomic-embed-text-v1.5
CORS_ORIGINS=http://localhost:3000
QDRANT_URL=http://localhost:6333
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=gink_dev_password
ENVIRONMENT=development
REDIS_URL=
SENTRY_DSN=
CLERK_JWKS_URL=$CLERK_JWKS_URL_DEV
CLERK_ISSUER=$CLERK_ISSUER_DEV
CLERK_SECRET_KEY=
CLERK_WEBHOOK_SECRET=
EOF
    ok ".env created"
  fi
  # Backfill keys added after first generation (idempotent)
  local f="$API_DIR/.env"
  grep -q '^ENVIRONMENT='          "$f" || echo "ENVIRONMENT=development"               >> "$f"
  grep -q '^REDIS_URL='            "$f" || echo "REDIS_URL="                            >> "$f"
  grep -q '^SENTRY_DSN='           "$f" || echo "SENTRY_DSN="                           >> "$f"
  grep -q '^QDRANT_URL='           "$f" || echo "QDRANT_URL=http://localhost:6333"      >> "$f"
  grep -q '^NEO4J_URI='            "$f" || echo "NEO4J_URI=bolt://localhost:7687"       >> "$f"
  grep -q '^NEO4J_USER='           "$f" || echo "NEO4J_USER=neo4j"                      >> "$f"
  grep -q '^NEO4J_PASSWORD='       "$f" || echo "NEO4J_PASSWORD=gink_dev_password"      >> "$f"
  grep -q '^CLERK_JWKS_URL='       "$f" || echo "CLERK_JWKS_URL=$CLERK_JWKS_URL_DEV"    >> "$f"
  grep -q '^CLERK_ISSUER='         "$f" || echo "CLERK_ISSUER=$CLERK_ISSUER_DEV"        >> "$f"
  grep -q '^CLERK_SECRET_KEY='     "$f" || echo "CLERK_SECRET_KEY="                     >> "$f"
  grep -q '^CLERK_WEBHOOK_SECRET=' "$f" || echo "CLERK_WEBHOOK_SECRET="                 >> "$f"

  # Frontend .env.local
  if [ ! -f "$WEB_DIR/.env.local" ]; then
    cat > "$WEB_DIR/.env.local" <<EOF
NEXT_PUBLIC_API_BASE_URL=http://localhost:8080
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=$CLERK_PK_DEV
CLERK_SECRET_KEY=
NEXT_PUBLIC_CLERK_SIGN_IN_URL=/login
NEXT_PUBLIC_CLERK_SIGN_UP_URL=/signup
NEXT_PUBLIC_CLERK_SIGN_IN_FALLBACK_REDIRECT_URL=/studio
NEXT_PUBLIC_CLERK_SIGN_UP_FALLBACK_REDIRECT_URL=/studio
EOF
  fi
  local w="$WEB_DIR/.env.local"
  grep -q '^NEXT_PUBLIC_API_BASE_URL='          "$w" || echo "NEXT_PUBLIC_API_BASE_URL=http://localhost:8080"  >> "$w"
  grep -q '^NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=' "$w" || echo "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=$CLERK_PK_DEV"  >> "$w"
  grep -q '^CLERK_SECRET_KEY='                  "$w" || echo "CLERK_SECRET_KEY="                                >> "$w"

  # Clerk secret presence check
  if ! grep -qE '^CLERK_SECRET_KEY=.+' "$API_DIR/.env" || ! grep -qE '^CLERK_SECRET_KEY=.+' "$w"; then
    wrn "CLERK_SECRET_KEY not set — sign-in/up will fail until you add sk_… to BOTH apps/api/.env and apps/web/.env.local"
  fi

  # Optional Docker services (Qdrant + Neo4j) — never fatal
  if command -v docker >/dev/null 2>&1 && timeout 8 docker info >/dev/null 2>&1; then
    inf "Starting Qdrant + Neo4j (docker compose)..."
    if docker compose -f "$ROOT/docker-compose.yml" up -d qdrant neo4j >/dev/null 2>&1; then
      ok "Qdrant :6333 + Neo4j :7474/:7687 up"
    else
      wrn "Could not start Qdrant/Neo4j (optional — RAG + graph degrade gracefully)"
    fi
  else
    wrn "Docker unavailable — Qdrant + Neo4j skipped (RAG + graph degrade gracefully)"
  fi

  # Migrations
  inf "Running DB migrations..."
  if ( cd "$API_DIR" && "$VENV_ALEMBIC" upgrade head >>"$LOG_DIR/migrate.log" 2>&1 ); then
    ok "Migrations up to date"
  else
    err "Migration failed — see $LOG_DIR/migrate.log"; exit 1
  fi
}

# ── start / stop ────────────────────────────────────────────────────────────────

start_api() {
  ( cd "$API_DIR" && exec "$VENV_UVICORN" app.main:app \
      --host 127.0.0.1 --port 8080 --reload --reload-dir "$API_DIR/app" --app-dir "$API_DIR" \
  ) >"$API_LOG" 2>&1 &
  echo $! > "$API_PIDF"
}

start_web() {
  ( cd "$WEB_DIR" && exec npm run dev ) >"$WEB_LOG" 2>&1 &
  echo $! > "$WEB_PIDF"
}

do_stop() {
  inf "Stopping api + web (Qdrant/Neo4j containers stay up)..."
  for f in "$API_PIDF" "$WEB_PIDF"; do
    if [ -f "$f" ]; then
      local pid; pid=$(cat "$f" 2>/dev/null)
      [ -n "$pid" ] && kill "$pid" 2>/dev/null
      rm -f "$f"
    fi
  done
  # Belt-and-suspenders: clear the ports even if pidfiles were stale.
  kill_port 8080
  kill_port 3000
  ok "stopped"
}

banner() {
  echo
  echo -e "${GRN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RST}"
  echo -e "  ${CYN}Hub${RST}      http://localhost:3000"
  echo -e "  ${CYN}API${RST}      http://localhost:8080"
  echo -e "  ${CYN}API docs${RST} http://localhost:8080/docs"
  echo -e "${GRN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RST}"
}

do_status() {
  is_running "$API_PIDF" && ok "api  running (pid $(cat "$API_PIDF"))" || wrn "api  not running"
  is_running "$WEB_PIDF" && ok "web  running (pid $(cat "$WEB_PIDF"))" || wrn "web  not running"
  if port_up 8080; then
    local h; h=$(curl -s -m 3 http://localhost:8080/health 2>/dev/null)
    [ -n "$h" ] && echo "  health: $h"
  fi
  port_up 3000 && ok "frontend reachable :3000" || wrn "frontend not reachable :3000"
}

# ── command dispatch ────────────────────────────────────────────────────────────

CMD="${1:-foreground}"
case "$CMD" in
  stop)    do_stop ;;
  status)  do_status ;;
  logs)    inf "tailing $LOG_DIR (Ctrl+C to stop tailing — servers keep running)"; tail -n 40 -f "$API_LOG" "$WEB_LOG" ;;
  restart) do_stop; sleep 1; exec "$ROOT/run.sh" start ;;

  start)   # detached — survives terminal close
    do_stop >/dev/null 2>&1
    setup
    inf "Launching api + web (detached)..."
    start_api
    start_web
    wait_for_port 8080 "api" 40
    wait_for_port 3000 "web" 40
    banner
    echo -e "  detached — logs: ${CYN}./run.sh logs${RST}   stop: ${CYN}./run.sh stop${RST}"
    echo
    ;;

  foreground|"")  # default — Ctrl+C stops both
    do_stop >/dev/null 2>&1
    setup
    trap 'echo; do_stop; exit 0' INT TERM
    inf "Launching api + web (foreground — Ctrl+C to stop)..."
    ( cd "$API_DIR" && exec "$VENV_UVICORN" app.main:app \
        --host 127.0.0.1 --port 8080 --reload --reload-dir "$API_DIR/app" --app-dir "$API_DIR" \
        2>&1 | sed -u 's/^/\x1b[36m[api]\x1b[0m /' ) &
    echo $! > "$API_PIDF"
    ( cd "$WEB_DIR" && npm run dev 2>&1 | sed -u 's/^/\x1b[32m[web]\x1b[0m /' ) &
    echo $! > "$WEB_PIDF"
    banner
    echo -e "  Ctrl+C stops api + web"
    echo
    wait
    ;;

  *) err "unknown command: $CMD"; echo "usage: ./run.sh [start|stop|restart|status|logs]"; exit 1 ;;
esac
