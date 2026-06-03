"""Polar (Merchant of Record) billing backend.

Polar is the seller of record, so it works for merchants in countries Stripe
doesn't directly support (e.g. Saudi Arabia) — no foreign entity needed, and it
remits global sales tax. Set BILLING_PROVIDER=polar, POLAR_ACCESS_TOKEN,
POLAR_WEBHOOK_SECRET, the per-tier POLAR_PRODUCT_* ids, and POLAR_SERVER.

Webhooks follow the Standard Webhooks spec: headers webhook-id / webhook-timestamp
/ webhook-signature, where the signature is base64(HMAC-SHA256(secret,
"{id}.{timestamp}.{raw-body}")) and the header is a space-separated list of
"v1,<sig>" tokens. The signing secret is base64 (optionally "whsec_"-prefixed).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import plans
from app.core.config import get_settings
from app.core.errors import BadRequest, Unauthorized
from app.db.models import Subscription, User
from app.services.billing.base import BillingEvent, BillingProvider, CheckoutResult, PortalResult

_STATUS_MAP = {
    "active": plans.STATUS_ACTIVE,
    "trialing": plans.STATUS_TRIALING,
    "past_due": plans.STATUS_PAST_DUE,
    "unpaid": plans.STATUS_PAST_DUE,
    "incomplete": plans.STATUS_PAST_DUE,
    "incomplete_expired": plans.STATUS_CANCELED,
    "canceled": plans.STATUS_CANCELED,
}


def _parse_dt(value) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


class PolarBillingProvider(BillingProvider):
    name = "polar"

    def _base_url(self) -> str:
        return "https://sandbox-api.polar.sh" if get_settings().polar_server == "sandbox" else "https://api.polar.sh"

    def _headers(self) -> dict:
        token = get_settings().polar_access_token
        if not token:
            raise BadRequest("Polar is not configured (POLAR_ACCESS_TOKEN missing).")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def _product_for(self, tier: str) -> str:
        s = get_settings()
        return {plans.DEV_AI: s.polar_product_dev_ai, plans.BYOK: s.polar_product_byok}.get(tier, "")

    def _tier_for_product(self, product_id: str) -> str:
        s = get_settings()
        mapping = {s.polar_product_dev_ai: plans.DEV_AI, s.polar_product_byok: plans.BYOK}
        return mapping.get(product_id, "") if product_id else ""

    async def create_checkout(
        self, db: AsyncSession, user: User, tier: str, *, success_url: str, cancel_url: str
    ) -> CheckoutResult:
        product = self._product_for(tier)
        if not product:
            raise BadRequest(f"No Polar product configured for the {tier} plan.")
        payload = {
            "products": [product],
            "success_url": success_url,
            "customer_email": user.email,
            "external_customer_id": user.id,   # lets us resolve the user on webhooks
            "metadata": {"user_id": user.id, "tier": tier},
        }
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                r = await client.post(f"{self._base_url()}/v1/checkouts/", headers=self._headers(), json=payload)
                r.raise_for_status()
                data = r.json()
        except httpx.HTTPStatusError as e:
            raise BadRequest(f"Polar checkout failed (HTTP {e.response.status_code}): {e.response.text[:200]}") from e
        except Exception as e:
            raise BadRequest(f"Polar checkout failed: {e}") from e
        return CheckoutResult(provider=self.name, url=data.get("url"), activated=False, tier=tier)

    async def create_portal(self, db: AsyncSession, user: User, *, return_url: str) -> PortalResult:
        sub = (await db.execute(
            select(Subscription)
            .where(Subscription.user_id == user.id, Subscription.provider == self.name)
            .order_by(Subscription.created_at.desc())
        )).scalars().first()
        if sub is None or not sub.external_customer_id:
            return PortalResult(provider=self.name, url=None,
                                message="No Polar customer on file yet — subscribe first.")
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                r = await client.post(f"{self._base_url()}/v1/customer-sessions/",
                                      headers=self._headers(), json={"customer_id": sub.external_customer_id})
                r.raise_for_status()
                data = r.json()
        except Exception as e:
            return PortalResult(provider=self.name, url=None, message=f"Couldn't open the billing portal: {e}")
        return PortalResult(provider=self.name, url=data.get("customer_portal_url"))

    # ── Webhook (Standard Webhooks) ───────────────────────────────────────────
    def _verify(self, body: bytes, headers: dict) -> None:
        secret = get_settings().polar_webhook_secret
        if not secret:
            raise Unauthorized("Polar webhook secret not configured.")
        wid = headers.get("webhook-id", "")
        wts = headers.get("webhook-timestamp", "")
        wsig = headers.get("webhook-signature", "")
        if not (wid and wts and wsig):
            raise Unauthorized("Missing Standard Webhooks headers.")
        raw = secret[len("whsec_"):] if secret.startswith("whsec_") else secret
        try:
            key = base64.b64decode(raw)
        except Exception:
            key = raw.encode()
        signed = f"{wid}.{wts}.".encode() + body
        expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
        # The header is a space-separated list of "v1,<sig>" (signatures may rotate).
        candidates = [p.split(",", 1)[1] if "," in p else p for p in wsig.split()]
        if not any(hmac.compare_digest(sig, expected) for sig in candidates):
            raise Unauthorized("Invalid Polar webhook signature.")

    async def parse_webhook(self, body: bytes, headers: dict) -> BillingEvent:
        self._verify(body, headers)
        try:
            event = json.loads(body.decode())
        except Exception as e:
            raise BadRequest(f"Malformed Polar webhook body: {e}") from e
        return self._map_event(event, headers.get("webhook-id", ""))

    def _map_event(self, event: dict, webhook_id: str) -> BillingEvent:
        etype = event.get("type", "")
        data = event.get("data") or {}
        meta = data.get("metadata") or {}
        customer = data.get("customer") or {}
        product_id = data.get("product_id") or (data.get("product") or {}).get("id", "") or ""
        # Resolve our user from checkout metadata, falling back to the external_id
        # we set on the customer at checkout time.
        user_id = meta.get("user_id") or customer.get("external_id")
        common = dict(
            provider=self.name,
            external_event_id=webhook_id,
            external_customer_id=data.get("customer_id") or customer.get("id", "") or "",
            raw=data,
        )

        if etype in ("subscription.created", "subscription.active", "subscription.updated", "subscription.uncanceled"):
            return BillingEvent(
                kind="activated" if etype == "subscription.created" else "updated",
                user_id=user_id,
                tier=self._tier_for_product(product_id),
                status=_STATUS_MAP.get(data.get("status", ""), plans.STATUS_ACTIVE),
                external_subscription_id=data.get("id", "") or "",
                current_period_end=_parse_dt(data.get("current_period_end")),
                cancel_at_period_end=bool(data.get("cancel_at_period_end")),
                **common,
            )
        if etype in ("subscription.canceled", "subscription.revoked"):
            return BillingEvent(
                kind="canceled", user_id=user_id, status=plans.STATUS_CANCELED,
                external_subscription_id=data.get("id", "") or "", **common,
            )
        if etype == "order.refunded":
            return BillingEvent(kind="canceled", user_id=user_id, status=plans.STATUS_CANCELED, **common)
        return BillingEvent(kind="ignored", **common)
