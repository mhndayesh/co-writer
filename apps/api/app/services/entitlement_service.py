"""Entitlement & usage metering — decides, for each AI call, whether the user
may run it and which key pays for it.

Read by `llm_service.run()` (the single AI choke point) before every call, and by
the billing router for the usage meter shown in the UI.

Usage is metered straight off the `llm_runs` audit log: we count rows whose
`key_source == "server"` (i.e. paid for by the house key). BYOK calls
(`key_source == "user"`) and degraded fallbacks (`key_source == "none"`) never
count against any limit.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import plans
from app.core.config import get_settings
from app.db.models import LLMRun, User
from app.services import site_config_service
from app.services.site_config_service import SiteConfig

# Tiers an owner may "shape-shift" into to test the real per-tier experience.
_SIMULATABLE = (plans.FREE, plans.DEV_AI, plans.BYOK)

# Diagnostic pages that must always run (so users can configure/verify keys even
# when their quota is spent). They still resolve a key source but skip metering.
UNMETERED_PAGES = {"llm.test"}

# The site owner / admins: unlimited, never-metered AI on the house models — they
# don't subscribe to their own product. Recognized by is_admin or ADMIN_EMAILS.
OWNER_TIER = "owner"
_OWNER_LIMIT = plans.PlanLimit(
    tier=OWNER_TIER, key_source="server", period="month",
    max_actions=None, max_tokens=None, requires_subscription=False,
)


def is_owner(user: User) -> bool:
    if getattr(user, "is_admin", False):
        return True
    email = (user.email or "").lower()
    return bool(email) and email in get_settings().admin_emails_list


@dataclass(frozen=True)
class Entitlement:
    plan_tier: str        # raw tier stored on the user
    plan_status: str      # raw status stored on the user
    effective_tier: str   # tier whose limits actually apply right now
    limit: plans.PlanLimit

    @property
    def key_source(self) -> str:
        return self.limit.key_source


@dataclass(frozen=True)
class Usage:
    actions_used: int
    tokens_used: int
    period: str                       # "lifetime" | "month"
    period_start: datetime | None     # None for lifetime


@dataclass(frozen=True)
class AiAuthorization:
    allowed: bool
    key_source: str                   # "server" | "user"
    reason: str = ""                  # "" | "trial_exhausted" | "quota_exceeded"
    message: str = ""


def get_entitlement(user: User, config: SiteConfig | None = None) -> Entitlement:
    """Resolve the tier whose limits apply *right now*. A paid tier whose
    subscription has lapsed (status not active/trialing) falls back to the free
    trial entitlement. Owners/admins always get the uncapped owner entitlement —
    UNLESS they've turned on "shape-shift" (`act_as_tier`), in which case they get
    that tier's full entitlement (caps, metering, key_source) so they can test the
    real experience. `config` carries the owner's DB-tuned caps (env fallback)."""
    if is_owner(user):
        act = (user.act_as_tier or "").strip()
        if act in _SIMULATABLE:
            return Entitlement(
                plan_tier=OWNER_TIER, plan_status=plans.STATUS_ACTIVE,
                effective_tier=act, limit=plans.plan_limit(act, config),
            )
        return Entitlement(
            plan_tier=OWNER_TIER, plan_status=plans.STATUS_ACTIVE,
            effective_tier=OWNER_TIER, limit=_OWNER_LIMIT,
        )

    raw_tier = user.plan_tier or plans.FREE
    raw_status = user.plan_status or plans.STATUS_NONE

    effective = raw_tier
    if raw_tier in plans.PAID_TIERS and raw_status not in plans.ACTIVE_STATUSES:
        effective = plans.FREE

    # Hard expiry (promo/manual grants): a paid tier past its plan_expires_at lapses
    # to free even if status still reads "active" — nothing else flips it. (Stripe
    # subs leave plan_expires_at NULL; their lapse is handled by webhooks.)
    if effective in plans.PAID_TIERS and getattr(user, "plan_expires_at", None) is not None:
        exp = user.plan_expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) >= exp:
            effective = plans.FREE

    return Entitlement(
        plan_tier=raw_tier,
        plan_status=raw_status,
        effective_tier=effective,
        limit=plans.plan_limit(effective, config),
    )


def _month_start() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def get_usage(db: AsyncSession, user: User, limit: plans.PlanLimit) -> Usage:
    """Count house-key ("server") AI usage in the limit's window."""
    period_start = None if limit.period == "lifetime" else _month_start()

    stmt = select(
        func.count(LLMRun.id),
        func.coalesce(func.sum(LLMRun.tokens_in + LLMRun.tokens_out), 0),
    ).where(
        LLMRun.user_id == user.id,
        LLMRun.key_source == "server",
    )
    if period_start is not None:
        stmt = stmt.where(LLMRun.created_at >= period_start)

    row = (await db.execute(stmt)).one()
    return Usage(
        actions_used=int(row[0] or 0),
        tokens_used=int(row[1] or 0),
        period=limit.period,
        period_start=period_start,
    )


async def authorize_ai(db: AsyncSession, user: User, page: str, *, meter: bool = True) -> AiAuthorization:
    """Decide whether `user` may run the AI task `page`, and which key pays.

    Never raises — callers (llm_service.run) translate a non-allowed result into
    the right typed HTTP error.
    """
    config = await site_config_service.get_site_config(db)
    ent = get_entitlement(user, config)
    limit = ent.limit

    # BYOK: always allowed here; a missing key is surfaced later at provider build.
    if limit.key_source == "user":
        return AiAuthorization(allowed=True, key_source="user")

    # House-key tiers (free trial + dev_ai). Diagnostics bypass the meter.
    if not meter or page in UNMETERED_PAGES:
        return AiAuthorization(allowed=True, key_source="server")

    usage = await get_usage(db, user, limit)
    over_actions = limit.max_actions is not None and usage.actions_used >= limit.max_actions
    over_tokens = limit.max_tokens is not None and usage.tokens_used >= limit.max_tokens
    if over_actions or over_tokens:
        if ent.effective_tier == plans.FREE:
            return AiAuthorization(
                allowed=False, key_source="server", reason="trial_exhausted",
                message="You've used your free AI trial. Subscribe to keep writing with AI.",
            )
        return AiAuthorization(
            allowed=False, key_source="server", reason="quota_exceeded",
            message="You've hit this month's AI usage limit. It resets at the start of next month.",
        )
    return AiAuthorization(allowed=True, key_source="server")


async def usage_summary(db: AsyncSession, user: User) -> dict:
    """Frontend-facing entitlement + meter snapshot."""
    config = await site_config_service.get_site_config(db)
    ent = get_entitlement(user, config)
    limit = ent.limit
    owner = is_owner(user)
    # "metered" = a house-key tier that actually has a cap to count against.
    # Owner/unlimited (caps None) and BYOK (own keys) are not metered.
    metered = limit.key_source == "server" and (limit.max_actions is not None or limit.max_tokens is not None)
    usage = await get_usage(db, user, limit) if metered else None

    def _remaining(used: int, cap: int | None) -> int | None:
        if cap is None:
            return None
        return max(0, cap - used)

    return {
        "plan_tier": ent.plan_tier,
        "plan_status": ent.plan_status,
        "effective_tier": ent.effective_tier,
        "key_source": ent.key_source,
        "metered": metered,
        "period": limit.period,
        "limits": {"max_actions": limit.max_actions, "max_tokens": limit.max_tokens},
        "usage": {
            "actions_used": usage.actions_used if usage else 0,
            "tokens_used": usage.tokens_used if usage else 0,
            "actions_remaining": _remaining(usage.actions_used, limit.max_actions) if usage else None,
            "tokens_remaining": _remaining(usage.tokens_used, limit.max_tokens) if usage else None,
        },
        # Can this user run an AI action right now? (cheap pre-check for UI locks)
        "ai_available": (await authorize_ai(db, user, "flow.polish")).allowed,
        # Owner-only "shape-shift": which tier the owner is currently viewing as
        # (None when not in test mode). `is_owner` is the REAL owner flag, kept
        # separate from `effective_tier` so owner-only UI persists while simulating.
        "acting_as": (user.act_as_tier if owner and (user.act_as_tier or "") in _SIMULATABLE else None),
        "is_owner": owner,
    }


async def token_stats(db: AsyncSession, user: User) -> dict:
    """All-time token totals for ONE user — every AI call, any tier/key/provider.

    A raw tally (not the plan meter): `tokens_in` = sent to the model (prompt),
    `tokens_out` = returned (completion). Used by the personal dev counter to
    estimate average usage per run.
    """
    row = (
        await db.execute(
            select(
                func.count(LLMRun.id),
                func.coalesce(func.sum(LLMRun.tokens_in), 0),
                func.coalesce(func.sum(LLMRun.tokens_out), 0),
            ).where(LLMRun.user_id == user.id)
        )
    ).one()
    runs = int(row[0] or 0)
    tokens_in = int(row[1] or 0)
    tokens_out = int(row[2] or 0)
    total = tokens_in + tokens_out

    def _avg(x: int) -> float:
        return round(x / runs, 1) if runs else 0.0

    return {
        "runs": runs,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "total": total,
        "avg_in": _avg(tokens_in),
        "avg_out": _avg(tokens_out),
        "avg_total": _avg(total),
    }
