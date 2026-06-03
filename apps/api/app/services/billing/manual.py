"""Manual billing — no real payment processor.

Activates a plan instantly. This is the default backend: it lets you ship and
test the whole tier/limit/lock system before pricing or a payment provider is
decided, and it's what admin plan-overrides flow through. Swap in Stripe (or any
other provider) by setting BILLING_PROVIDER without touching the rest of the app.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import plans
from app.db.models import User
from app.services.billing.base import BillingEvent, BillingProvider, CheckoutResult, PortalResult


class ManualBillingProvider(BillingProvider):
    name = "manual"

    async def create_checkout(
        self, db: AsyncSession, user: User, tier: str, *, success_url: str, cancel_url: str
    ) -> CheckoutResult:
        event = BillingEvent(
            kind="activated",
            user_id=user.id,
            tier=tier,
            status=plans.STATUS_ACTIVE,
            provider=self.name,
        )
        return CheckoutResult(provider=self.name, url=success_url, activated=True, tier=tier, event=event)

    async def create_portal(self, db: AsyncSession, user: User, *, return_url: str) -> PortalResult:
        return PortalResult(
            provider=self.name,
            url=None,
            message="Plan changes are handled manually right now — contact support.",
        )

    async def parse_webhook(self, body: bytes, headers: dict) -> BillingEvent:
        return BillingEvent(kind="ignored", provider=self.name)
