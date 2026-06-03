"""Promo / gift code redemption + hard plan expiry."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

import app.db.models as m
from app.core import plans
from app.core.errors import BadRequest
from app.db.session import SessionLocal
from app.services import billing_service, entitlement_service, redemption_service


@pytest_asyncio.fixture()
async def owner_and_users():
    async with SessionLocal() as s:
        owner = m.User(email=f"owner-{uuid.uuid4().hex}@x.z")
        u1 = m.User(email=f"u1-{uuid.uuid4().hex}@x.z")
        u2 = m.User(email=f"u2-{uuid.uuid4().hex}@x.z")
        s.add_all([owner, u1, u2])
        await s.commit()
        return {"owner": owner.id, "u1": u1.id, "u2": u2.id}


@pytest.mark.asyncio
async def test_redeem_grants_tier_then_lapses(owner_and_users):
    async with SessionLocal() as s:
        owner = await s.get(m.User, owner_and_users["owner"])
        code = await redemption_service.create_code(s, owner, tier="dev_ai", duration_days=30)
        await s.commit()
        code_str = code.code

    # Redeem → dev_ai with an expiry.
    async with SessionLocal() as s:
        u = await s.get(m.User, owner_and_users["u1"])
        res = await redemption_service.redeem_code(s, u, code_str)
        await s.commit()
        assert res["tier"] == "dev_ai"
        assert res["lifetime"] is False

    # Entitlement now reflects dev_ai.
    async with SessionLocal() as s:
        u = await s.get(m.User, owner_and_users["u1"])
        assert entitlement_service.get_entitlement(u, None).effective_tier == plans.DEV_AI
        assert u.plan_expires_at is not None

        # One redemption per user.
        with pytest.raises(BadRequest):
            await redemption_service.redeem_code(s, u, code_str)

    # Force the grant past its expiry → lapses to free even though status is active.
    async with SessionLocal() as s:
        u = await s.get(m.User, owner_and_users["u1"])
        u.plan_expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        await s.commit()
        assert entitlement_service.get_entitlement(u, None).effective_tier == plans.FREE


@pytest.mark.asyncio
async def test_lifetime_code_never_expires(owner_and_users):
    async with SessionLocal() as s:
        owner = await s.get(m.User, owner_and_users["owner"])
        code = await redemption_service.create_code(s, owner, tier="byok", duration_days=None)
        await s.commit()
        code_str = code.code
    async with SessionLocal() as s:
        u = await s.get(m.User, owner_and_users["u1"])
        res = await redemption_service.redeem_code(s, u, code_str)
        await s.commit()
        assert res["lifetime"] is True
        assert u.plan_expires_at is None
        assert entitlement_service.get_entitlement(u, None).effective_tier == plans.BYOK


@pytest.mark.asyncio
async def test_redeem_same_tier_stacks(owner_and_users):
    async with SessionLocal() as s:
        owner = await s.get(m.User, owner_and_users["owner"])
        c1 = await redemption_service.create_code(s, owner, tier="dev_ai", duration_days=30)
        c2 = await redemption_service.create_code(s, owner, tier="dev_ai", duration_days=30)
        await s.commit()
        code1, code2 = c1.code, c2.code

    async with SessionLocal() as s:
        u = await s.get(m.User, owner_and_users["u1"])
        await redemption_service.redeem_code(s, u, code1)
        await s.commit()
        exp1 = u.plan_expires_at

    async with SessionLocal() as s:
        u = await s.get(m.User, owner_and_users["u1"])
        res = await redemption_service.redeem_code(s, u, code2)
        await s.commit()
        exp2 = u.plan_expires_at

    assert res["extended"] is True
    # The second 30-day code stacked on the remaining time (~30 days later),
    # rather than resetting the expiry to now+30 (which would be ~0 days apart).
    assert (exp2 - exp1).days >= 29


@pytest.mark.asyncio
async def test_redeem_blocked_with_active_stripe(owner_and_users):
    async with SessionLocal() as s:
        owner = await s.get(m.User, owner_and_users["owner"])
        c = await redemption_service.create_code(s, owner, tier="dev_ai", duration_days=30)
        await s.commit()
        code = c.code

    async with SessionLocal() as s:
        u2 = await s.get(m.User, owner_and_users["u2"])
        await billing_service.set_plan(s, u2, "dev_ai", provider="stripe")
        await s.commit()

    async with SessionLocal() as s:
        u2 = await s.get(m.User, owner_and_users["u2"])
        with pytest.raises(BadRequest):
            await redemption_service.redeem_code(s, u2, code)


@pytest.mark.asyncio
async def test_max_uses_enforced(owner_and_users):
    async with SessionLocal() as s:
        owner = await s.get(m.User, owner_and_users["owner"])
        code = await redemption_service.create_code(s, owner, tier="dev_ai", duration_days=7, max_uses=1)
        await s.commit()
        code_str = code.code
    async with SessionLocal() as s:
        u1 = await s.get(m.User, owner_and_users["u1"])
        await redemption_service.redeem_code(s, u1, code_str)
        await s.commit()
    async with SessionLocal() as s:
        u2 = await s.get(m.User, owner_and_users["u2"])
        with pytest.raises(BadRequest):
            await redemption_service.redeem_code(s, u2, code_str)
