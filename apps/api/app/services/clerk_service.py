"""Clerk ↔ local user bridge.

Clerk owns identity (credentials, email verification, SSO); the local `users`
table stays the source of truth for everything the app builds on top of an
identity (stories, billing, profile). This module keeps the two in sync:

- `resolve_user(claims, db)` — called on every authenticated request. Maps a
  verified Clerk session token to a local user row, linking by clerk_user_id
  first, then by email (adopting a pre-existing password-auth account), and
  lazily provisioning a fresh row if neither matches.
- `upsert_from_webhook(payload, db)` — keeps rows current from Clerk's
  user.created/updated/deleted events (see app/api/v1/clerk_webhook.py).

Email/name aren't in Clerk's default session token, so when a row must be
created we backfill them from the Clerk Backend API using the secret key.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import User

log = logging.getLogger("gink.clerk")

_CLERK_API = "https://api.clerk.com/v1"


async def _fetch_clerk_user(clerk_id: str) -> dict[str, Any] | None:
    """Fetch a user from the Clerk Backend API. Returns None on any failure
    (network / missing key) — callers fall back to claim-derived data."""
    s = get_settings()
    if not s.clerk_secret_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                f"{_CLERK_API}/users/{clerk_id}",
                headers={"Authorization": f"Bearer {s.clerk_secret_key}"},
            )
            r.raise_for_status()
            return r.json()
    except Exception:
        log.warning("Clerk Backend API fetch failed for %s", clerk_id, exc_info=True)
        return None


def _primary_email(clerk_user: dict[str, Any]) -> str | None:
    pid = clerk_user.get("primary_email_address_id")
    for e in clerk_user.get("email_addresses", []) or []:
        if e.get("id") == pid and e.get("email_address"):
            return e["email_address"]
    # fall back to the first address if no primary flagged
    for e in clerk_user.get("email_addresses", []) or []:
        if e.get("email_address"):
            return e["email_address"]
    return None


def _email_verified(clerk_user: dict[str, Any], email: str) -> bool:
    """True only if Clerk reports the given address as verified."""
    for e in clerk_user.get("email_addresses", []) or []:
        if e.get("email_address") == email:
            return ((e.get("verification") or {}).get("status")) == "verified"
    return False


def _is_sensitive_account(user: User, email: str) -> bool:
    """An account worth protecting from email-match adoption: site admins and
    anyone on an active paid plan. Hijacking these has real blast radius."""
    from app.core import plans

    if getattr(user, "is_admin", False):
        return True
    if email.lower() in get_settings().admin_emails_list:
        return True
    return (user.plan_tier in plans.PAID_TIERS) and (user.plan_status in plans.ACTIVE_STATUSES)


def _display_name(clerk_user: dict[str, Any], email: str | None) -> str:
    first = (clerk_user.get("first_name") or "").strip()
    last = (clerk_user.get("last_name") or "").strip()
    name = (f"{first} {last}").strip()
    if name:
        return name
    uname = (clerk_user.get("username") or "").strip()
    if uname:
        return uname
    return (email or "").split("@")[0]


async def resolve_user(claims: dict[str, Any], db: AsyncSession) -> User:
    """Map verified Clerk session-token claims to a local User, creating/linking
    as needed. Commits any change it makes so the row is durable for this and
    subsequent requests."""
    clerk_id = claims.get("sub")
    if not clerk_id:
        raise ValueError("Clerk token missing sub")

    # 1. Already linked — the common path.
    user = (await db.execute(select(User).where(User.clerk_user_id == clerk_id))).scalar_one_or_none()
    if user is not None:
        return user

    # Email may be present as a custom session claim; otherwise hit the Backend API.
    email = claims.get("email")
    clerk_user = None
    if not email:
        clerk_user = await _fetch_clerk_user(clerk_id)
        if clerk_user:
            email = _primary_email(clerk_user)

    # 2. Adopt an existing local account with the same email (legacy password user
    #    signing in through Clerk for the first time).
    if email:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is not None:
            # Adoption-by-email is an account-takeover path if Clerk ever admits an
            # UNVERIFIED address. For sensitive accounts (admin / active paid), demand
            # a verified email before linking — otherwise refuse the sign-in.
            if _is_sensitive_account(user, email):
                verified = claims.get("email_verified") is True
                if not verified:
                    if clerk_user is None:
                        clerk_user = await _fetch_clerk_user(clerk_id)
                    verified = bool(clerk_user) and _email_verified(clerk_user, email)
                if not verified:
                    log.warning(
                        "Refusing Clerk adoption of sensitive account %s (%s): email not verified",
                        user.id, email,
                    )
                    raise ValueError("email not verified for sensitive account adoption")
            user.clerk_user_id = clerk_id
            await db.commit()
            await db.refresh(user)
            log.info("Linked existing user %s to Clerk id %s", user.id, clerk_id)
            return user

    # 3. Provision a fresh row.
    if not email:
        # No email anywhere — can't satisfy the NOT NULL/unique email column.
        raise ValueError("Cannot provision user: no email in Clerk token or Backend API")
    if clerk_user is None:
        clerk_user = await _fetch_clerk_user(clerk_id) or {}
    user = User(
        email=email,
        password_hash=None,
        clerk_user_id=clerk_id,
        display_name=_display_name(clerk_user, email),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    log.info("Provisioned new user %s from Clerk id %s", user.id, clerk_id)
    return user


async def revoke_user_sessions(clerk_id: str) -> int:
    """Force-logout: revoke every active Clerk session for a user via the Backend
    API. Returns the number revoked (0 if Clerk isn't configured / on any failure).

    Clerk session *tokens* are short-lived, but the underlying Clerk *session* is
    long-lived — this is what lets the backend kill a compromised session before
    natural expiry (the legacy path uses users.token_version for the same purpose)."""
    s = get_settings()
    if not s.clerk_secret_key or not clerk_id:
        return 0
    headers = {"Authorization": f"Bearer {s.clerk_secret_key}"}
    revoked = 0
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                f"{_CLERK_API}/sessions",
                params={"user_id": clerk_id, "status": "active"},
                headers=headers,
            )
            r.raise_for_status()
            body = r.json()
            sessions = body if isinstance(body, list) else (body.get("data") or [])
            for sess in sessions:
                sid = sess.get("id")
                if not sid:
                    continue
                rr = await client.post(f"{_CLERK_API}/sessions/{sid}/revoke", headers=headers)
                if rr.status_code < 300:
                    revoked += 1
    except Exception:
        log.warning("Failed to revoke Clerk sessions for %s", clerk_id, exc_info=True)
    return revoked


async def upsert_from_webhook(event_type: str, data: dict[str, Any], db: AsyncSession) -> None:
    """Apply a Clerk user.* webhook event to the local users table."""
    clerk_id = data.get("id")
    if not clerk_id:
        return

    if event_type == "user.deleted":
        user = (await db.execute(select(User).where(User.clerk_user_id == clerk_id))).scalar_one_or_none()
        if user is not None:
            # Unlink rather than hard-delete: keeps the user's stories/data intact
            # (the table is our backup of record). A re-signup re-links by email.
            user.clerk_user_id = None
            await db.commit()
        return

    # user.created / user.updated — payload is the full Clerk user object.
    email = _primary_email(data)
    if not email:
        log.warning("Clerk webhook %s for %s had no email; skipping", event_type, clerk_id)
        return

    user = (await db.execute(select(User).where(User.clerk_user_id == clerk_id))).scalar_one_or_none()
    if user is None:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()

    if user is None:
        user = User(
            email=email,
            password_hash=None,
            clerk_user_id=clerk_id,
            display_name=_display_name(data, email),
        )
        db.add(user)
    else:
        user.clerk_user_id = clerk_id
        user.email = email
        if not user.display_name:
            user.display_name = _display_name(data, email)
    await db.commit()
