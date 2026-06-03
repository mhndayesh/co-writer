"""Subscription tiers and their limits — the single source of truth for what
each plan can do. The actual numbers live in `core.config.Settings` (env-tunable)
so they can be changed without a code edit; this module assembles them into a
small table the rest of the app reads.

Three tiers:
  free    — manual writing is always free; AI assists run on the website's house
            ("dev AI") key but only up to a small *lifetime* trial allowance.
  dev_ai  — paid. AI runs on the house key with *monthly* action + token caps.
  byok    — paid, fixed price. AI runs ONLY on the user's own keys; the house key
            is never used and there is no usage meter on our side.

Key source decides who pays for a call: "server" = our house key (free + dev_ai),
"user" = the subscriber's BYOK key.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.config import get_settings

if TYPE_CHECKING:
    from app.services.site_config_service import SiteConfig


def _pick(db_val: int | None, env_val: int | None) -> int | None:
    """Owner-tuned DB value wins when set; otherwise the env default."""
    return db_val if db_val is not None else env_val

# Tier identifiers (stored on users.plan_tier and subscriptions.tier).
FREE = "free"
DEV_AI = "dev_ai"
BYOK = "byok"
TIERS = (FREE, DEV_AI, BYOK)

# Paid tiers a user can subscribe to.
PAID_TIERS = (DEV_AI, BYOK)

# Plan statuses (users.plan_status / subscriptions.status).
STATUS_NONE = "none"
STATUS_TRIALING = "trialing"
STATUS_ACTIVE = "active"
STATUS_PAST_DUE = "past_due"
STATUS_CANCELED = "canceled"
# Statuses that grant access to a paid tier's entitlements.
ACTIVE_STATUSES = (STATUS_ACTIVE, STATUS_TRIALING)


@dataclass(frozen=True)
class PlanLimit:
    tier: str
    key_source: str          # "server" (house key) | "user" (BYOK key)
    period: str              # "lifetime" | "month"
    max_actions: int | None  # None = unlimited
    max_tokens: int | None   # None = unlimited
    requires_subscription: bool  # free=False; paid tiers=True


def plan_limit(tier: str, config: "SiteConfig | None" = None) -> PlanLimit:
    """Resolve the live limit for a tier. Caps come from the owner's DB config
    (`config`) when set, else the env-tunable defaults (get_settings() is
    lru_cached, so the env path stays cheap). BYOK is always uncapped."""
    s = get_settings()
    if tier == DEV_AI:
        return PlanLimit(
            tier=DEV_AI, key_source="server", period="month",
            max_actions=_pick(config and config.dev_ai_max_actions, s.dev_ai_max_actions_per_month),
            max_tokens=_pick(config and config.dev_ai_max_tokens, s.dev_ai_max_tokens_per_month),
            requires_subscription=True,
        )
    if tier == BYOK:
        return PlanLimit(
            tier=BYOK, key_source="user", period="month",
            max_actions=None, max_tokens=None,  # uncapped on our side
            requires_subscription=True,
        )
    # Default / free trial.
    return PlanLimit(
        tier=FREE, key_source="server", period="lifetime",
        max_actions=_pick(config and config.free_trial_max_actions, s.free_trial_max_actions),
        max_tokens=_pick(config and config.free_trial_max_tokens, s.free_trial_max_tokens),
        requires_subscription=False,
    )


def plan_descriptor(tier: str) -> dict:
    """Public, frontend-facing description of a plan (no secrets)."""
    lim = plan_limit(tier)
    labels = {
        FREE: ("Free", "Try the AI writing tools on us — a handful of assists to start."),
        DEV_AI: ("Plus", "Write with G-Ink's built-in models. Monthly allowance, no keys to manage."),
        BYOK: ("Bring Your Own Key", "Use your own provider keys. Unlimited on our side, fixed price."),
    }
    # Display price only — the amount actually charged is set on the Stripe Price.
    prices: dict[str, tuple[float | None, str]] = {
        FREE: (None, "Free"),
        DEV_AI: (19.99, "$19.99/mo"),
        BYOK: (4.99, "$4.99/mo"),
    }
    name, blurb = labels.get(tier, (tier, ""))
    price, price_label = prices.get(tier, (None, ""))
    return {
        "tier": tier,
        "name": name,
        "blurb": blurb,
        "key_source": lim.key_source,
        "period": lim.period,
        "max_actions": lim.max_actions,
        "max_tokens": lim.max_tokens,
        "requires_subscription": lim.requires_subscription,
        "price": price,
        "price_label": price_label,
    }
