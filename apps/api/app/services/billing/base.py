"""The billing provider contract + the normalized types that cross it.

Providers are *pure*: they create checkout/portal sessions and parse webhooks,
but they never touch the database. All DB writes (creating/updating the
`subscriptions` row and syncing the user's cached tier) happen in
`billing_service.apply_event`, driven by the `BillingEvent` a provider returns.
That keeps every backend interchangeable and the persistence logic in one place.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User


@dataclass
class BillingEvent:
    """A normalized subscription state-change, regardless of provider."""
    kind: str = "ignored"   # "activated" | "updated" | "canceled" | "ignored"
    user_id: Optional[str] = None
    tier: str = ""
    status: str = ""        # one of app.core.plans statuses
    provider: str = ""
    external_event_id: str = ""  # provider's event id — used for webhook idempotency
    external_customer_id: str = ""
    external_subscription_id: str = ""
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    cancel_at_period_end: bool = False
    raw: dict = field(default_factory=dict)


@dataclass
class CheckoutResult:
    provider: str
    url: Optional[str] = None     # redirect target (None when activated inline)
    activated: bool = False       # True → the router applies `event` immediately
    tier: str = ""
    event: Optional[BillingEvent] = None


@dataclass
class PortalResult:
    provider: str
    url: Optional[str] = None
    message: str = ""


class BillingProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def create_checkout(
        self, db: AsyncSession, user: User, tier: str, *, success_url: str, cancel_url: str
    ) -> CheckoutResult:
        """Start a subscription purchase for `tier`."""

    @abstractmethod
    async def create_portal(self, db: AsyncSession, user: User, *, return_url: str) -> PortalResult:
        """Open a self-service management/cancellation session."""

    @abstractmethod
    async def parse_webhook(self, body: bytes, headers: dict) -> BillingEvent:
        """Verify + translate an inbound provider webhook into a BillingEvent."""
