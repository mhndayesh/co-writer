"""Stripe billing backend.

Scaffolded and ready: set BILLING_PROVIDER=stripe, STRIPE_SECRET_KEY,
STRIPE_WEBHOOK_SECRET, and the per-tier STRIPE_PRICE_* ids. The `stripe` package
is imported lazily so the app runs fine without it installed when using manual
billing. The webhook is signature-verified; events are mapped to BillingEvents
and persisted by billing_service.apply_event.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import plans
from app.core.config import get_settings
from app.core.errors import BadRequest, Unauthorized
from app.db.models import Subscription, User
from app.services.billing.base import BillingEvent, BillingProvider, CheckoutResult, PortalResult

# Stripe subscription status → our plan status.
_STATUS_MAP = {
    "active": plans.STATUS_ACTIVE,
    "trialing": plans.STATUS_TRIALING,
    "past_due": plans.STATUS_PAST_DUE,
    "unpaid": plans.STATUS_PAST_DUE,
    "canceled": plans.STATUS_CANCELED,
    "incomplete": plans.STATUS_PAST_DUE,
    "incomplete_expired": plans.STATUS_CANCELED,
}


def _ts(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except Exception:
        return None


class StripeBillingProvider(BillingProvider):
    name = "stripe"

    def _stripe(self):
        try:
            import stripe
        except ImportError as e:  # pragma: no cover - depends on optional dep
            raise BadRequest("Stripe SDK is not installed on the server.") from e
        s = get_settings()
        if not s.stripe_secret_key:
            raise BadRequest("Stripe is not configured (STRIPE_SECRET_KEY missing).")
        stripe.api_key = s.stripe_secret_key
        return stripe

    def _price_for(self, tier: str) -> str:
        s = get_settings()
        return {plans.DEV_AI: s.stripe_price_dev_ai, plans.BYOK: s.stripe_price_byok}.get(tier, "")

    def _tier_for_price(self, price_id: str) -> str:
        """Authoritative tier = the price actually purchased (NOT client metadata,
        which a user could tamper with to pay for the cheap plan and receive the
        expensive one)."""
        if not price_id:
            return ""
        s = get_settings()
        return {s.stripe_price_dev_ai: plans.DEV_AI, s.stripe_price_byok: plans.BYOK}.get(price_id, "")

    def _tier_from_obj(self, obj: dict) -> str:
        """Pull the price id from a subscription or (expanded) checkout-session
        object and map it to our tier. Returns "" when no known price is found."""
        price_id = ""
        try:
            items = (obj.get("items") or {}).get("data") or []
            if items:
                price_id = (items[0].get("price") or {}).get("id", "") or ""
            if not price_id:
                line_items = (obj.get("line_items") or {}).get("data") or []
                if line_items:
                    price_id = (line_items[0].get("price") or {}).get("id", "") or ""
            if not price_id:
                price_id = (obj.get("plan") or {}).get("id", "") or ""
        except Exception:
            price_id = ""
        return self._tier_for_price(price_id)

    async def create_checkout(
        self, db: AsyncSession, user: User, tier: str, *, success_url: str, cancel_url: str
    ) -> CheckoutResult:
        stripe = self._stripe()
        price = self._price_for(tier)
        if not price:
            raise BadRequest(f"No Stripe price configured for the {tier} plan.")
        meta = {"user_id": user.id, "tier": tier}
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=user.email,
            client_reference_id=user.id,
            metadata=meta,
            subscription_data={"metadata": meta},
        )
        return CheckoutResult(provider=self.name, url=session.url, activated=False, tier=tier)

    async def create_portal(self, db: AsyncSession, user: User, *, return_url: str) -> PortalResult:
        stripe = self._stripe()
        sub = (
            await db.execute(
                select(Subscription)
                .where(Subscription.user_id == user.id, Subscription.provider == self.name)
                .order_by(Subscription.created_at.desc())
            )
        ).scalars().first()
        if sub is None or not sub.external_customer_id:
            raise BadRequest("No Stripe customer on file for this account.")
        portal = stripe.billing_portal.Session.create(
            customer=sub.external_customer_id, return_url=return_url
        )
        return PortalResult(provider=self.name, url=portal.url)

    async def parse_webhook(self, body: bytes, headers: dict) -> BillingEvent:
        stripe = self._stripe()
        s = get_settings()
        sig = headers.get("stripe-signature") or headers.get("Stripe-Signature", "")
        try:
            event = stripe.Webhook.construct_event(body, sig, s.stripe_webhook_secret)
        except Exception as e:  # signature / payload error
            raise Unauthorized(f"Invalid Stripe webhook signature: {e}") from e
        return self._map_event(event)

    def _map_event(self, event) -> BillingEvent:
        etype = event["type"]
        event_id = event.get("id", "") or ""
        obj = event["data"]["object"]
        meta = obj.get("metadata") or {}

        if etype == "checkout.session.completed":
            # Tier comes from the purchased price when available; metadata is only
            # used for user identity, never to decide the granted tier. If the
            # price isn't on the (un-expanded) session, leave tier empty — the
            # subscription.created/updated event sets it authoritatively from price.
            return BillingEvent(
                kind="activated",
                user_id=meta.get("user_id") or obj.get("client_reference_id"),
                tier=self._tier_from_obj(obj),
                status=plans.STATUS_ACTIVE,
                provider=self.name,
                external_customer_id=obj.get("customer", "") or "",
                external_subscription_id=obj.get("subscription", "") or "",
                external_event_id=event_id,
                raw=dict(obj),
            )
        if etype in ("customer.subscription.created", "customer.subscription.updated"):
            return BillingEvent(
                kind="updated",
                user_id=meta.get("user_id"),
                tier=self._tier_from_obj(obj),  # authoritative: from the price purchased
                status=_STATUS_MAP.get(obj.get("status", ""), plans.STATUS_ACTIVE),
                provider=self.name,
                external_customer_id=obj.get("customer", "") or "",
                external_subscription_id=obj.get("id", "") or "",
                current_period_start=_ts(obj.get("current_period_start")),
                current_period_end=_ts(obj.get("current_period_end")),
                cancel_at_period_end=bool(obj.get("cancel_at_period_end")),
                external_event_id=event_id,
                raw=dict(obj),
            )
        if etype == "customer.subscription.deleted":
            return BillingEvent(
                kind="canceled",
                user_id=meta.get("user_id"),
                status=plans.STATUS_CANCELED,
                provider=self.name,
                external_customer_id=obj.get("customer", "") or "",
                external_subscription_id=obj.get("id", "") or "",
                external_event_id=event_id,
                raw=dict(obj),
            )
        # A refund / chargeback / dispute means the user paid and took it back —
        # revoke paid access. The object here is a charge/dispute, so resolve the
        # user via the stored customer id.
        if etype in ("charge.refunded", "charge.dispute.created", "charge.dispute.funds_withdrawn"):
            return BillingEvent(
                kind="canceled",
                status=plans.STATUS_CANCELED,
                provider=self.name,
                external_customer_id=(obj.get("customer", "") or ""),
                external_event_id=event_id,
                raw=dict(obj),
            )
        return BillingEvent(kind="ignored", provider=self.name, external_event_id=event_id)
