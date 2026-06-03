"""Polar (MoR) webhook signature verification + event mapping."""
import base64
import hashlib
import hmac
import json

import pytest

from app.core import plans
from app.core.config import get_settings
from app.core.errors import Unauthorized
from app.services.billing.polar_provider import PolarBillingProvider

_SECRET = "whsec_" + base64.b64encode(b"polar-test-signing-secret-0001").decode()


@pytest.fixture(autouse=True)
def _polar_env(monkeypatch):
    monkeypatch.setenv("POLAR_WEBHOOK_SECRET", _SECRET)
    monkeypatch.setenv("POLAR_PRODUCT_DEV_AI", "prod_plus_123")
    monkeypatch.setenv("POLAR_PRODUCT_BYOK", "prod_byok_456")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _sign(body: bytes, wid="msg_1", wts="1717400000") -> dict:
    key = base64.b64decode(_SECRET[len("whsec_"):])
    sig = base64.b64encode(hmac.new(key, f"{wid}.{wts}.".encode() + body, hashlib.sha256).digest()).decode()
    return {"webhook-id": wid, "webhook-timestamp": wts, "webhook-signature": f"v1,{sig}"}


@pytest.mark.asyncio
async def test_valid_subscription_event_maps_to_tier():
    p = PolarBillingProvider()
    body = json.dumps({
        "type": "subscription.active",
        "data": {
            "id": "sub_abc",
            "status": "active",
            "product_id": "prod_plus_123",
            "customer_id": "cus_9",
            "current_period_end": "2026-07-01T00:00:00Z",
            "metadata": {"user_id": "user_42"},
        },
    }).encode()
    event = await p.parse_webhook(body, _sign(body))
    assert event.kind == "updated"
    assert event.tier == plans.DEV_AI
    assert event.status == plans.STATUS_ACTIVE
    assert event.user_id == "user_42"
    assert event.external_subscription_id == "sub_abc"
    assert event.external_event_id == "msg_1"  # idempotency key = webhook-id
    assert event.current_period_end is not None


@pytest.mark.asyncio
async def test_tampered_body_rejected():
    p = PolarBillingProvider()
    body = json.dumps({"type": "subscription.active", "data": {}}).encode()
    headers = _sign(body)
    tampered = body + b" "  # signature no longer matches
    with pytest.raises(Unauthorized):
        await p.parse_webhook(tampered, headers)


@pytest.mark.asyncio
async def test_refund_cancels():
    p = PolarBillingProvider()
    body = json.dumps({"type": "order.refunded", "data": {"customer_id": "cus_9"}}).encode()
    event = await p.parse_webhook(body, _sign(body))
    assert event.kind == "canceled"
    assert event.status == plans.STATUS_CANCELED
