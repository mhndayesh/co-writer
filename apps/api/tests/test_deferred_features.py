"""Tests for the hardening features: refresh-token rotation/revocation, Stripe
webhook idempotency + price-derived tier + refunds, the rating/review read-gate,
and LLM streaming. (Migration drift is covered in test_migration_drift.py.)"""
import pytest
from sqlalchemy.exc import IntegrityError

from app.core import plans
from app.core.config import get_settings
from app.core.errors import BadRequest, NotFound
from app.db.models import BillingEventRecord, Story, User
from app.db.publishing_models import Publication, PublicationChapter
from app.db.publishing_schemas import ProgressUpdate, RatingSubmit, ReviewSubmit
from app.db.session import SessionLocal
from app.services import reader_service, social_service
from app.services.billing.stripe_provider import StripeBillingProvider


async def _mk_user(db, email: str) -> User:
    u = User(email=email, password_hash="x", display_name="t")
    db.add(u)
    await db.flush()
    return u


# ─────────────────────────── refresh-token rotation ───────────────────────────

@pytest.mark.asyncio
async def test_refresh_rotates_and_detects_reuse(client):
    r = await client.post("/v1/auth/signup", json={"email": "rotate@example.com", "password": "password123"})
    assert r.status_code == 200, r.text
    rt = r.json()["data"]["tokens"]["refresh_token"]

    # First refresh works and returns a DIFFERENT refresh token (rotation).
    r2 = await client.post("/v1/auth/refresh", json={"refresh_token": rt})
    assert r2.status_code == 200, r2.text
    new_rt = r2.json()["data"]["tokens"]["refresh_token"]
    assert new_rt != rt

    # Replaying the OLD (now-revoked) token is rejected AND kills the family.
    r3 = await client.post("/v1/auth/refresh", json={"refresh_token": rt})
    assert r3.status_code == 401

    # The freshly-minted token is now revoked too (reuse → whole family revoked).
    r4 = await client.post("/v1/auth/refresh", json={"refresh_token": new_rt})
    assert r4.status_code == 401


@pytest.mark.asyncio
async def test_logout_invalidates_access_and_refresh(client):
    r = await client.post("/v1/auth/signup", json={"email": "logout@example.com", "password": "password123"})
    tokens = r.json()["data"]["tokens"]
    H = {"Authorization": f"Bearer {tokens['access_token']}"}

    assert (await client.get("/v1/auth/me", headers=H)).status_code == 200
    assert (await client.post("/v1/auth/logout", headers=H)).status_code == 200

    # Access token is dead (token_version bumped), refresh token revoked.
    assert (await client.get("/v1/auth/me", headers=H)).status_code == 401
    r2 = await client.post("/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r2.status_code == 401


# ─────────────────────────── Stripe webhook hardening ──────────────────────────

def test_stripe_tier_comes_from_price_not_metadata():
    s = get_settings()
    prev = (s.stripe_price_dev_ai, s.stripe_price_byok)
    s.stripe_price_dev_ai = "price_devai_123"
    s.stripe_price_byok = "price_byok_456"
    try:
        p = StripeBillingProvider()
        # metadata LIES (claims byok) but the purchased price is dev_ai → dev_ai wins.
        event = {
            "id": "evt_1",
            "type": "customer.subscription.updated",
            "data": {"object": {
                "id": "sub_1", "status": "active", "customer": "cus_1",
                "metadata": {"user_id": "u1", "tier": plans.BYOK},
                "items": {"data": [{"price": {"id": "price_devai_123"}}]},
            }},
        }
        be = p._map_event(event)
        assert be.tier == plans.DEV_AI
        assert be.external_event_id == "evt_1"

        # A refund maps to a cancellation (revoke paid access) and keeps the id.
        refund = {"id": "evt_2", "type": "charge.refunded", "data": {"object": {"customer": "cus_1"}}}
        be2 = p._map_event(refund)
        assert be2.kind == "canceled"
        assert be2.external_event_id == "evt_2"
    finally:
        s.stripe_price_dev_ai, s.stripe_price_byok = prev


@pytest.mark.asyncio
async def test_billing_event_idempotency_unique_constraint():
    async with SessionLocal() as db:
        db.add(BillingEventRecord(provider="stripe", external_event_id="evt_dup"))
        await db.commit()  # must persist for the next session to see the conflict

    # The same (provider, external_event_id) cannot be recorded twice.
    async with SessionLocal() as db:
        db.add(BillingEventRecord(provider="stripe", external_event_id="evt_dup"))
        with pytest.raises(IntegrityError):
            await db.flush()


# ─────────────────────────── rating/review read-gate ──────────────────────────

async def _publish_one_chapter(db, slug: str):
    writer = await _mk_user(db, f"writer-{slug}@test.com")
    reader = await _mk_user(db, f"reader-{slug}@test.com")
    story = Story(user_id=writer.id, title="Pub")
    db.add(story)
    await db.flush()
    pub = Publication(story_id=story.id, user_id=writer.id, slug=slug, status="published")
    db.add(pub)
    await db.flush()
    db.add(PublicationChapter(
        publication_id=pub.id, chapter_number=1, version=1,
        title="Ch1", content="Once upon a time.", is_latest=True,
    ))
    await db.flush()
    return pub, reader


@pytest.mark.asyncio
async def test_progress_rejects_nonexistent_chapter_and_gate_requires_real_read():
    async with SessionLocal() as db:
        pub, reader = await _publish_one_chapter(db, "gate-slug-1")

        # Faking progress on a chapter that doesn't exist is rejected — this is
        # what previously let anyone unlock rating/reviewing without reading.
        with pytest.raises(NotFound):
            await reader_service.update_progress(
                "gate-slug-1", ProgressUpdate(chapter_number=99, completion_percentage=50.0), reader.id, db
            )

        # No genuine progress yet → rating and review are both gated.
        with pytest.raises(BadRequest):
            await social_service.upsert_rating(pub.id, RatingSubmit(overall=5), reader.id, db)
        with pytest.raises(BadRequest):
            await social_service.submit_review(pub.id, ReviewSubmit(body="Nice read, very compelling."), reader.id, db)

        # Real progress on a real chapter → the gate opens.
        await reader_service.update_progress(
            "gate-slug-1", ProgressUpdate(chapter_number=1, completion_percentage=80.0), reader.id, db
        )
        rating = await social_service.upsert_rating(pub.id, RatingSubmit(overall=5), reader.id, db)
        assert rating.overall == 5


@pytest.mark.asyncio
async def test_progress_rejects_unpublished_publication():
    async with SessionLocal() as db:
        writer = await _mk_user(db, "draft-writer@test.com")
        reader = await _mk_user(db, "draft-reader@test.com")
        story = Story(user_id=writer.id, title="Draft")
        db.add(story)
        await db.flush()
        pub = Publication(story_id=story.id, user_id=writer.id, slug="draft-slug", status="draft")
        db.add(pub)
        await db.flush()
        db.add(PublicationChapter(
            publication_id=pub.id, chapter_number=1, version=1,
            title="Ch1", content="hidden", is_latest=True,
        ))
        await db.flush()

        # A draft is not readable → progress (and thus the gate) is unavailable.
        with pytest.raises(NotFound):
            await reader_service.update_progress(
                "draft-slug", ProgressUpdate(chapter_number=1, completion_percentage=10.0), reader.id, db
            )


# ─────────────────────────────── LLM streaming ────────────────────────────────

@pytest.mark.asyncio
async def test_companion_stream_emits_sse_frames(client):
    r = await client.post("/v1/auth/signup", json={"email": "streamer@example.com", "password": "password123"})
    H = {"Authorization": f"Bearer {r.json()['data']['tokens']['access_token']}"}
    sid = (await client.post("/v1/stories", json={"title": "S"}, headers=H)).json()["data"]["story"]["id"]

    # lmstudio is unreachable in tests → the provider stream errors and the
    # deterministic fallback streams instead. We just assert SSE framing + close.
    r2 = await client.post(
        f"/v1/stories/{sid}/flow/companion/stream",
        json={"instruction": "Write an opening line."},
        headers=H,
    )
    assert r2.status_code == 200, r2.text
    assert "text/event-stream" in r2.headers.get("content-type", "")
    body = r2.text
    assert "data:" in body
    assert '"done": true' in body
