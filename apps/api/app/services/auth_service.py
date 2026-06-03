"""Session/token lifecycle: issue, rotate, and revoke refresh tokens.

Refresh tokens are stateless JWTs, but each carries a `jti` backed by a
`refresh_tokens` row so they can be rotated and revoked (a plain JWT can't be).
Access tokens carry a `tv` (token version) matched against `users.token_version`
so logout / password change can invalidate every outstanding access token at
once.

Rotation: /refresh revokes the presented row and mints a fresh pair. Presenting
an already-revoked refresh token means it leaked and was replayed → revoke the
whole family and bump token_version (defensive: kills any tokens the thief holds).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import Unauthorized
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.db.models import RefreshToken, User
from app.db.schemas import TokenPair

log = logging.getLogger("gink.auth")


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _mint(db: AsyncSession, user: User) -> tuple[TokenPair, str]:
    """Create a refresh_tokens row + a matching token pair. Returns (pair, jti)."""
    s = get_settings()
    jti = uuid.uuid4().hex
    db.add(RefreshToken(
        jti=jti,
        user_id=user.id,
        expires_at=_now() + timedelta(days=s.refresh_token_ttl_days),
    ))
    await db.flush()
    pair = TokenPair(
        access_token=create_access_token(user.id, token_version=user.token_version or 0),
        refresh_token=create_refresh_token(user.id, jti=jti),
    )
    return pair, jti


async def issue_token_pair(db: AsyncSession, user: User) -> TokenPair:
    """Fresh login/signup: mint a new access+refresh pair."""
    pair, _ = await _mint(db, user)
    return pair


async def rotate(db: AsyncSession, raw_refresh_token: str) -> TokenPair:
    """Validate + rotate a refresh token. Raises Unauthorized on any problem."""
    try:
        claims = decode_token(raw_refresh_token)
    except Exception:
        log.warning("refresh token decode failed", exc_info=True)
        raise Unauthorized("Invalid or expired refresh token") from None
    if claims.get("type") != "refresh":
        raise Unauthorized("Not a refresh token")

    user_id = claims.get("sub")
    jti = claims.get("jti")
    if not user_id or not jti:
        raise Unauthorized("Invalid refresh token")

    user = await db.get(User, user_id)
    if user is None:
        raise Unauthorized("User not found")

    # SELECT … FOR UPDATE: acquires a row-level lock so two concurrent /refresh
    # calls with the same token cannot both read revoked=False, both mint a new
    # pair, and both commit — which would fork the session and defeat reuse
    # detection. The second request blocks here until the first commits, then
    # sees revoked=True and triggers the reuse-detection path.
    stmt = (
        select(RefreshToken)
        .where(RefreshToken.jti == jti)
        .with_for_update()
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None or row.user_id != user_id:
        raise Unauthorized("Invalid refresh token")

    if row.revoked:
        # An already-rotated/revoked token is being replayed → token theft.
        # Revoke the entire family so neither party can keep refreshing. Commit
        # the revocation NOW — we're about to raise, and the route's commit won't
        # run, so without this the family-kill would roll back.
        log.warning("refresh token reuse detected for user %s; revoking all sessions", user_id)
        await revoke_all(db, user)
        await db.commit()
        raise Unauthorized("Refresh token reuse detected; all sessions revoked")

    # SQLite returns naive datetimes even for tz-aware columns; normalize to UTC
    # before comparing so we don't blow up on naive-vs-aware.
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < _now():
        raise Unauthorized("Refresh token expired")

    new_pair, new_jti = await _mint(db, user)
    row.revoked = True
    row.replaced_by = new_jti
    await db.flush()
    return new_pair


async def revoke_all(db: AsyncSession, user: User) -> None:
    """Revoke every refresh token for the user and bump token_version so all
    outstanding ACCESS tokens are immediately invalid too (logout / kill-switch)."""
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked == False)  # noqa: E712
        .values(revoked=True)
    )
    user.token_version = (user.token_version or 0) + 1
    await db.flush()


async def logout(db: AsyncSession, user: User) -> None:
    """End all sessions for the user (revokes refresh tokens + invalidates access
    tokens via the token_version bump)."""
    await revoke_all(db, user)
