#!/bin/bash
# Postgres backup with a restore-test, failure alerting, and an optional offsite
# copy. A dump that never restores isn't a backup — so every run loads the fresh
# dump into a throwaway DB and sanity-checks it before declaring success.
set -euo pipefail

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups"
DB_HOST="${POSTGRES_HOST:-postgres}"
DB_USER="${POSTGRES_USER:-gink}"
DB_NAME="${POSTGRES_DB:-gink}"
DUMP="$BACKUP_DIR/gink_${TIMESTAMP}.sql.gz"

# Optional ops integrations (no-ops unless set in the environment):
#   BACKUP_ALERT_WEBHOOK — POSTed to on ANY failure (so a broken cron isn't silent).
#   BACKUP_OFFSITE_CMD   — shell command run with $DUMP to copy the dump off-host
#                          (e.g. "aws s3 cp \"$DUMP\" s3://my-bucket/").
ALERT_WEBHOOK="${BACKUP_ALERT_WEBHOOK:-}"

_alert() {
  echo "[backup] FAILED at stage '${1:-unknown}' for gink_${TIMESTAMP}" >&2
  if [ -n "$ALERT_WEBHOOK" ]; then
    wget -q -O /dev/null --post-data="gink backup FAILED: stage=${1:-unknown} ts=${TIMESTAMP}" \
      "$ALERT_WEBHOOK" 2>/dev/null || true
  fi
}
trap '_alert "${STAGE:-unknown}"' ERR

mkdir -p "$BACKUP_DIR"

STAGE="dump"
pg_dump -h "$DB_HOST" -U "$DB_USER" "$DB_NAME" | gzip > "$DUMP"

STAGE="verify-gzip"
gzip -t "$DUMP"
test -s "$DUMP"  # non-empty

# Restore-test: load the dump into a throwaway DB and confirm a known table exists,
# then drop it. Catches a silently-corrupt dump NOW instead of during a real outage.
STAGE="restore-test"
TEST_DB="gink_restore_test_${TIMESTAMP}"
dropdb -h "$DB_HOST" -U "$DB_USER" --if-exists "$TEST_DB" >/dev/null 2>&1 || true
createdb -h "$DB_HOST" -U "$DB_USER" "$TEST_DB"
trap 'dropdb -h "$DB_HOST" -U "$DB_USER" --if-exists "$TEST_DB" >/dev/null 2>&1 || true; _alert "${STAGE:-unknown}"' ERR
gunzip -c "$DUMP" | psql -h "$DB_HOST" -U "$DB_USER" -d "$TEST_DB" -q -v ON_ERROR_STOP=1 >/dev/null
psql -h "$DB_HOST" -U "$DB_USER" -d "$TEST_DB" -tAc "SELECT to_regclass('public.users') IS NOT NULL" | grep -q t
dropdb -h "$DB_HOST" -U "$DB_USER" --if-exists "$TEST_DB" >/dev/null 2>&1 || true
trap '_alert "${STAGE:-unknown}"' ERR

# Optional offsite copy — a same-host-only backup is lost with the host.
if [ -n "${BACKUP_OFFSITE_CMD:-}" ]; then
  STAGE="offsite"
  DUMP="$DUMP" sh -c "$BACKUP_OFFSITE_CMD"
fi

# Retain backups for 14 days
STAGE="prune"
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +14 -delete

echo "[backup] completed + restore-tested: gink_${TIMESTAMP}.sql.gz"
