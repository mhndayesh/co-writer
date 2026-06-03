"""Owner-minted promo / gift codes that grant a paid tier for a period.

Free subscriptions handed out by the owner — no payment provider involved. Redeem
goes through billing_service.set_plan(provider="promo", expires_at=…) so the grant
uses the same entitlement machinery as a paid plan and lapses on schedule.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import plans
from app.core.errors import BadRequest, Conflict, NotFound
from app.db.models import CodeRedemption, RedemptionCode, Subscription, User
from app.services import billing_service

# Unambiguous alphabet (no 0/O/1/I/L) for human-typable codes.
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gen_code(blocks: int = 3, block_len: int = 4) -> str:
    return "-".join("".join(secrets.choice(_ALPHABET) for _ in range(block_len)) for _ in range(blocks))


def _norm(code: str | None) -> str:
    return (code or "").strip().upper()


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def create_code(
    db: AsyncSession,
    owner: User,
    *,
    tier: str,
    duration_days: int | None,
    max_uses: int | None = None,
    note: str = "",
    code: str | None = None,
    code_expires_at: datetime | None = None,
) -> RedemptionCode:
    if tier not in plans.PAID_TIERS:
        raise BadRequest("Tier must be a paid tier (dev_ai or byok).")
    if duration_days is not None and duration_days <= 0:
        raise BadRequest("duration_days must be positive, or null for lifetime.")
    if max_uses is not None and max_uses <= 0:
        raise BadRequest("max_uses must be positive, or null for unlimited.")

    c = _norm(code) if code else _gen_code()
    if not (3 <= len(c) <= 64):
        raise BadRequest("Code must be 3–64 characters.")
    if (await db.execute(select(RedemptionCode).where(RedemptionCode.code == c))).scalar_one_or_none():
        raise Conflict("That code already exists — pick another.")

    row = RedemptionCode(
        code=c, tier=tier, duration_days=duration_days, max_uses=max_uses,
        note=(note or "")[:200], expires_at=code_expires_at, created_by=owner.id,
    )
    db.add(row)
    await db.flush()
    return row


async def redeem_code(db: AsyncSession, user: User, code: str) -> dict:
    c = _norm(code)
    if not c:
        raise BadRequest("Enter a code.")

    row = (await db.execute(select(RedemptionCode).where(RedemptionCode.code == c))).scalar_one_or_none()
    if row is None or not row.active:
        raise NotFound("That code isn’t valid.")
    if row.expires_at is not None and _now() >= _aware(row.expires_at):
        raise BadRequest("This code has expired.")
    if row.max_uses is not None and row.uses >= row.max_uses:
        raise BadRequest("This code has been fully redeemed.")

    already = (await db.execute(
        select(CodeRedemption).where(
            CodeRedemption.code_id == row.id, CodeRedemption.user_id == user.id
        )
    )).scalar_one_or_none()
    if already:
        raise BadRequest("You’ve already redeemed this code.")

    # Never clobber an active auto-renewing (paid) subscription with a free grant.
    latest_sub = (await db.execute(
        select(Subscription).where(Subscription.user_id == user.id).order_by(Subscription.created_at.desc())
    )).scalars().first()
    if latest_sub is not None and latest_sub.status in plans.ACTIVE_STATUSES \
            and latest_sub.provider in billing_service._AUTO_RENEW_PROVIDERS:
        raise BadRequest("You already have an active paid subscription — a code can’t be applied on top of it.")

    now = _now()
    # Stack the period instead of overwriting: if the user already has THIS tier
    # active with time remaining, add on top of what's left (and never downgrade a
    # lifetime grant to a timed one). Otherwise it's a fresh grant / tier switch.
    cur_exp = _aware(user.plan_expires_at)
    same_tier_active = (
        user.plan_status in plans.ACTIVE_STATUSES
        and user.plan_tier == row.tier
        and (cur_exp is None or cur_exp > now)
    )
    if row.duration_days is None:
        expires_at = None                                  # code grants lifetime
    elif same_tier_active and cur_exp is None:
        expires_at = None                                  # already lifetime on this tier → keep it
    elif same_tier_active:
        expires_at = cur_exp + timedelta(days=row.duration_days)   # extend remaining time
    else:
        expires_at = now + timedelta(days=row.duration_days)       # fresh / switching tier

    await billing_service.set_plan(db, user, row.tier, provider="promo", expires_at=expires_at)
    db.add(CodeRedemption(code_id=row.id, user_id=user.id, tier=row.tier, expires_at=expires_at))
    row.uses = (row.uses or 0) + 1
    await db.flush()

    return {
        "tier": row.tier,
        "lifetime": expires_at is None,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "extended": same_tier_active,
    }


async def list_codes(db: AsyncSession, *, limit: int = 200) -> list[dict]:
    rows = (await db.execute(
        select(RedemptionCode).order_by(RedemptionCode.created_at.desc()).limit(limit)
    )).scalars().all()
    return [serialize(r) for r in rows]


async def deactivate_code(db: AsyncSession, code_id: str) -> None:
    row = await db.get(RedemptionCode, code_id)
    if row is None:
        raise NotFound("Code not found.")
    row.active = False
    await db.flush()


def serialize(r: RedemptionCode) -> dict:
    return {
        "id": r.id,
        "code": r.code,
        "tier": r.tier,
        "duration_days": r.duration_days,
        "max_uses": r.max_uses,
        "uses": r.uses,
        "note": r.note,
        "active": r.active,
        "expires_at": r.expires_at.isoformat() if r.expires_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }
