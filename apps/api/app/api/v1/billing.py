"""Billing & subscription endpoints (provider-agnostic).

  GET  /v1/billing/plans              public plan catalog (limits, prices TBD)
  GET  /v1/billing/me                 current entitlement + usage meter
  POST /v1/billing/checkout           start a subscription for a tier
  POST /v1/billing/portal             manage/cancel an existing subscription
  POST /v1/billing/webhook/{provider} inbound provider webhook (no auth; verified)
"""
from fastapi import APIRouter, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core import plans
from app.core.config import get_settings
from app.core.deps import CurrentUser, DB
from app.core.errors import envelope_ok
from app.db.models import BillingEventRecord
from app.db.schemas import CheckoutRequest, RedeemCodeRequest
from app.services import billing_service, entitlement_service, redemption_service
from app.services.billing.registry import get_billing_provider

router = APIRouter()


@router.get("/plans")
async def get_plans():
    """Public — used by the pricing page. No secrets, no auth."""
    return envelope_ok({"plans": [plans.plan_descriptor(t) for t in plans.TIERS]})


@router.get("/me")
async def my_subscription(user: CurrentUser, db: DB):
    return envelope_ok(await entitlement_service.usage_summary(db, user))


@router.get("/token-stats")
async def get_token_stats(user: CurrentUser, db: DB):
    """Raw all-time token tally for the CURRENT user only (scoped by user_id)."""
    return envelope_ok(await entitlement_service.token_stats(db, user))


@router.post("/redeem")
async def redeem(payload: RedeemCodeRequest, user: CurrentUser, db: DB):
    """Redeem a promo/gift code → grants the code's tier for its period."""
    result = await redemption_service.redeem_code(db, user, payload.code)
    await db.commit()
    # Return the redemption outcome + the refreshed entitlement so the UI updates.
    result["entitlement"] = await entitlement_service.usage_summary(db, user)
    return envelope_ok(result)


@router.post("/checkout")
async def checkout(payload: CheckoutRequest, user: CurrentUser, db: DB):
    s = get_settings()
    provider = get_billing_provider()
    result = await provider.create_checkout(
        db, user, payload.tier,
        success_url=payload.success_url or s.billing_success_url,
        cancel_url=payload.cancel_url or s.billing_cancel_url,
    )
    # Manual provider activates inline; Stripe defers to the webhook.
    if result.event is not None:
        await billing_service.apply_event(db, result.event)
    await db.commit()
    return envelope_ok({
        "provider": result.provider,
        "url": result.url,
        "activated": result.activated,
        "tier": result.tier,
    })


@router.post("/portal")
async def portal(user: CurrentUser, db: DB):
    s = get_settings()
    provider = get_billing_provider()
    result = await provider.create_portal(db, user, return_url=s.billing_success_url)
    return envelope_ok({"provider": result.provider, "url": result.url, "message": result.message})


@router.post("/webhook/{provider_name}")
async def webhook(provider_name: str, request: Request, db: DB):
    provider = get_billing_provider()
    body = await request.body()
    event = await provider.parse_webhook(body, dict(request.headers))

    # Idempotency: providers deliver at-least-once and retry. Record the event id
    # first; if it's already been processed (or races a concurrent delivery via
    # the unique constraint), skip re-applying its side effects.
    eid = (event.external_event_id or "").strip()
    pname = event.provider or provider_name
    if eid:
        seen = (await db.execute(
            select(BillingEventRecord).where(
                BillingEventRecord.provider == pname,
                BillingEventRecord.external_event_id == eid,
            )
        )).scalar_one_or_none()
        if seen is not None:
            return envelope_ok({"received": True, "applied": False, "duplicate": True})
        db.add(BillingEventRecord(provider=pname, external_event_id=eid))
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            return envelope_ok({"received": True, "applied": False, "duplicate": True})

    sub = await billing_service.apply_event(db, event)
    if sub is None:
        # Nothing was applied (e.g. the user isn't resolvable yet, or a no-op
        # event). Roll back so the idempotency record is NOT persisted — a later
        # retry, once the user exists, can still be processed instead of being
        # permanently dropped as a duplicate.
        await db.rollback()
        return envelope_ok({"received": True, "applied": False})
    await db.commit()
    return envelope_ok({"received": True, "applied": True})
