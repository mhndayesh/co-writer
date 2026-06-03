"""Idempotency for client-initiated mutations that aren't naturally idempotent.

Flow `approve` and publish `push` each create new rows every time they run. If a
client retries one after a flaky-connection timeout, the atomic transaction only
prevents *partial* writes — not a duplicate *whole* operation (a second chapter,
an extra chapter version). This guards against that.

The client sends an `Idempotency-Key` header (any unique string per logical
operation). We key on `(user_id, scope, key)`:

  * `replay()` — called BEFORE running the work. If this key already ran, returns
    the original response so the route can short-circuit. Handles the common case
    (sequential retry after a timeout).
  * `remember()` — called AFTER the work commits, storing the response for replay.
    A concurrent double-submit that races past `replay()` collides on the unique
    constraint; `remember()` swallows that IntegrityError (the row is already
    there) so the second request still returns a valid response.

No-op when the header is absent, so callers that don't send a key are unaffected.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import IdempotencyKey

# Cap header length so a hostile client can't store oversized rows.
_MAX_KEY_LEN = 128


def _clean(key: str | None) -> str | None:
    if not key:
        return None
    key = key.strip()
    if not key:
        return None
    return key[:_MAX_KEY_LEN]


async def replay(db: AsyncSession, user_id: str, key: str | None, scope: str) -> dict | None:
    """Return the stored response for a previously-seen key, else None."""
    key = _clean(key)
    if key is None:
        return None
    row = (
        await db.execute(
            select(IdempotencyKey).where(
                IdempotencyKey.user_id == user_id,
                IdempotencyKey.scope == scope,
                IdempotencyKey.idem_key == key,
            )
        )
    ).scalar_one_or_none()
    return row.response if row is not None else None


async def remember(db: AsyncSession, user_id: str, key: str | None, scope: str, response: dict) -> None:
    """Persist the response for this key. Safe to call with no key (no-op)."""
    key = _clean(key)
    if key is None:
        return
    db.add(IdempotencyKey(user_id=user_id, scope=scope, idem_key=key, response=response))
    try:
        await db.commit()
    except IntegrityError:
        # A concurrent request already recorded this key — that's fine.
        await db.rollback()


async def prune_expired(db: AsyncSession, max_age_days: int = 7) -> int:
    """Delete idempotency rows older than the retry window so the table can't grow
    unbounded. A key only matters for the brief retry window after an operation, so
    a week is generous. Best-effort; meant to be called from the ARQ cron."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    result = await db.execute(delete(IdempotencyKey).where(IdempotencyKey.created_at < cutoff))
    await db.commit()
    return result.rowcount or 0
