"""Provider routing tests for the 3-lane LLM router.

No network calls here: the tests assert the resolved provider name only.

Lane routing only applies to BYOK users (they run on their own keys); free/Dev-AI
users always route to the house ("dev AI") provider regardless of their lanes —
that distinction is covered in test_subscriptions.py. So the users here are made
BYOK with placeholder keys so their lane config is honored.
"""
import pytest

from app.core import plans
from app.core.security import encrypt_secret
from app.db.models import User, UserLLMSettings
from app.db.session import SessionLocal
from app.services.llm.factory import get_embedding_provider, get_provider_for_page


def _lane(provider: str) -> dict:
    return {
        "provider": provider,
        "base_url": "",
        "model": "",
        "embed_model": "",
        # Encrypted placeholder so a BYOK build sees a real key (round-trips
        # through decrypt_secret whether or not a Fernet key is configured).
        "api_key_ciphertext": encrypt_secret("test-key"),
    }


async def _mk_user(db, email: str, tier: str = plans.BYOK) -> User:
    u = User(
        email=email, password_hash="x", display_name="t",
        plan_tier=tier, plan_status=plans.STATUS_ACTIVE,
    )
    db.add(u)
    await db.flush()
    return u


async def _set_lanes(db, user: User, **lanes: str) -> UserLLMSettings:
    row = await db.get(UserLLMSettings, user.id)
    if row is None:
        row = UserLLMSettings(user_id=user.id, lanes={})
        db.add(row)
    current = dict(row.lanes or {})
    for lane, provider in lanes.items():
        current[lane] = _lane(provider)
    row.lanes = current
    await db.flush()
    return row


@pytest.mark.asyncio
async def test_unified_config_routes_everything_to_same_provider():
    async with SessionLocal() as db:
        u = await _mk_user(db, "single@test.com")
        await _set_lanes(db, u, creative="openai", technical="openai", embedding="openai")

        for page in ("flow.polish", "flow.extract", "story_check", "flow.companion", "llm.test"):
            prov = await get_provider_for_page(db, u, page)
            assert prov.name == "openai", page


@pytest.mark.asyncio
async def test_router_routes_pages_by_category_lane():
    async with SessionLocal() as db:
        u = await _mk_user(db, "lanes@test.com")
        await _set_lanes(db, u, creative="anthropic", technical="lmstudio")

        for page in ("flow.polish", "story_check", "flow.companion"):
            assert (await get_provider_for_page(db, u, page)).name == "anthropic", page
        for page in ("flow.extract", "llm.test"):
            assert (await get_provider_for_page(db, u, page)).name == "lmstudio", page


@pytest.mark.asyncio
async def test_missing_lane_falls_back_to_env_default():
    async with SessionLocal() as db:
        u = await _mk_user(db, "missing-lane@test.com")
        await _set_lanes(db, u, creative="anthropic")

        assert (await get_provider_for_page(db, u, "flow.polish")).name == "anthropic"
        assert (await get_provider_for_page(db, u, "flow.extract")).name == "lmstudio"


@pytest.mark.asyncio
async def test_unknown_pages_default_to_technical_lane():
    async with SessionLocal() as db:
        u = await _mk_user(db, "unknown-page@test.com")
        await _set_lanes(db, u, creative="anthropic", technical="openrouter")

        assert (await get_provider_for_page(db, u, "some.new.task")).name == "openrouter"


@pytest.mark.asyncio
async def test_embedding_never_uses_non_embedding_provider():
    async with SessionLocal() as db:
        u = await _mk_user(db, "embed@test.com")
        await _set_lanes(db, u, creative="anthropic", technical="openrouter", embedding="anthropic")

        prov = await get_embedding_provider(db, u)
        assert prov.name == "lmstudio"

        await _set_lanes(db, u, embedding="openai")
        assert (await get_embedding_provider(db, u)).name == "openai"
