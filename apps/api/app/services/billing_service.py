"""Persistence for billing — the ONLY place that writes `subscriptions` and
syncs the user's cached tier. Providers hand it a normalized `BillingEvent`
(from checkout or a webhook); this applies it idempotently.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import plans
from app.db.models import Subscription, User
from app.services.billing.base import BillingEvent


def _now() -> datetime:
    return datetime.now(timezone.utc)


# Providers whose subscriptions auto-renew → no HARD plan_expires_at cutoff
# (lapse is driven by their webhooks). Promo/manual grants DO set a hard expiry.
_AUTO_RENEW_PROVIDERS = {"stripe"}


def _sync_user_cache(user: User, sub: Subscription) -> None:
    """Mirror the subscription's effective state onto the user's fast-read columns."""
    if sub.status in plans.ACTIVE_STATUSES:
        user.plan_tier = sub.tier
        user.plan_status = sub.status
        # Auto-renewing providers have no hard cutoff; clear any stale promo expiry.
        # Promo/manual grants leave it for set_plan() to set explicitly below.
        if sub.provider in _AUTO_RENEW_PROVIDERS:
            user.plan_expires_at = None
    elif sub.status == plans.STATUS_PAST_DUE:
        # Keep the tier label but entitlement downgrades to free (status not active).
        user.plan_tier = sub.tier
        user.plan_status = plans.STATUS_PAST_DUE
    else:  # canceled / unknown → back to free
        user.plan_tier = plans.FREE
        user.plan_status = plans.STATUS_NONE
        user.plan_expires_at = None


async def _resolve_user_id(db: AsyncSession, event: BillingEvent) -> str | None:
    if event.user_id:
        return event.user_id
    # Webhooks for subscription.updated/deleted may not carry our metadata; refund/
    # dispute events only carry a customer id — map back via stored ids.
    for col, val in (
        (Subscription.external_subscription_id, event.external_subscription_id),
        (Subscription.external_customer_id, event.external_customer_id),
    ):
        if val:
            sub = (
                await db.execute(
                    select(Subscription)
                    .where(col == val)
                    .order_by(Subscription.created_at.desc())
                )
            ).scalars().first()
            if sub:
                return sub.user_id
    return None


async def apply_event(db: AsyncSession, event: BillingEvent) -> Subscription | None:
    """Upsert the subscription row for an event and sync the user cache.

    Returns the affected Subscription, or None if the event was ignored or could
    not be matched to a user. Caller is responsible for committing.
    """
    if event.kind == "ignored":
        return None

    user_id = await _resolve_user_id(db, event)
    if not user_id:
        return None
    user = await db.get(User, user_id)
    if user is None:
        return None

    sub: Subscription | None = None
    if event.external_subscription_id:
        sub = (
            await db.execute(
                select(Subscription).where(
                    Subscription.external_subscription_id == event.external_subscription_id
                )
            )
        ).scalars().first()
    if sub is None:
        sub = (
            await db.execute(
                select(Subscription)
                .where(Subscription.user_id == user_id)
                .order_by(Subscription.created_at.desc())
            )
        ).scalars().first()
    if sub is None:
        sub = Subscription(user_id=user_id, provider=event.provider or "manual", tier=event.tier or plans.FREE)
        db.add(sub)

    # Stale-event guard: never move a CANCELED subscription back to ACTIVE from
    # an older event. Stripe can retry a late "subscription.updated(active)" after
    # a "subscription.deleted(canceled)" has already been applied — without this
    # guard a refunded/cancelled user regains paid access.
    if (
        event.status in plans.ACTIVE_STATUSES
        and sub.status == plans.STATUS_CANCELED
        and event.kind not in ("activated",)  # fresh checkout always allowed
    ):
        # Silently ignore the stale activation; don't update anything.
        return sub

    if event.tier:
        sub.tier = event.tier
    if event.status:
        sub.status = event.status
    if event.provider:
        sub.provider = event.provider
    if event.external_customer_id:
        sub.external_customer_id = event.external_customer_id
    if event.external_subscription_id:
        sub.external_subscription_id = event.external_subscription_id
    if event.current_period_start:
        sub.current_period_start = event.current_period_start
    if event.current_period_end:
        sub.current_period_end = event.current_period_end
    sub.cancel_at_period_end = event.cancel_at_period_end
    if event.raw:
        sub.raw = event.raw
    sub.updated_at = _now()

    _sync_user_cache(user, sub)
    await db.flush()
    return sub


async def set_plan(
    db: AsyncSession, user: User, tier: str, *, status: str | None = None,
    provider: str = "manual", expires_at: datetime | None = None,
) -> Subscription | None:
    """Directly set a user's plan (admin override / manual provider / promo code).

    `expires_at` sets a HARD cutoff (None = no expiry / lifetime); entitlement lapses
    the paid tier to free once it passes. Used by promo-code redemption so a granted
    period actually ends without any payment provider in the loop."""
    if tier == plans.FREE:
        status = plans.STATUS_CANCELED  # downgrade → user cache reset to free
    else:
        status = status or plans.STATUS_ACTIVE
    sub = await apply_event(
        db, BillingEvent(kind="activated", user_id=user.id, tier=tier, status=status, provider=provider)
    )
    if tier != plans.FREE:
        # Mirror the hard expiry onto the user (read by entitlement) + the sub record.
        user.plan_expires_at = expires_at
        if sub is not None:
            sub.current_period_end = expires_at
            sub.cancel_at_period_end = expires_at is not None
        await db.flush()
    return sub
