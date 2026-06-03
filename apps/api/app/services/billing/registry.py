"""Select the active billing backend from config (BILLING_PROVIDER)."""
from __future__ import annotations

from app.core.config import get_settings
from app.services.billing.base import BillingProvider
from app.services.billing.manual import ManualBillingProvider
from app.services.billing.polar_provider import PolarBillingProvider
from app.services.billing.stripe_provider import StripeBillingProvider

_PROVIDERS = {
    "manual": ManualBillingProvider,
    "stripe": StripeBillingProvider,
    "polar": PolarBillingProvider,
}


def get_billing_provider() -> BillingProvider:
    name = get_settings().billing_provider
    cls = _PROVIDERS.get(name, ManualBillingProvider)
    return cls()
