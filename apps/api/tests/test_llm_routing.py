"""Provider routing resolution tests — no network, assert provider .name.

Verifies the three modes (single / split / custom) route each task `page`
to the right provider, and that embeddings never land on a non-embed provider.
"""
import pytest
from sqlalchemy import select

from app.db.models import LLMProfile, User, UserLLMSettings
from app.db.session import SessionLocal
from app.services.llm.factory import get_embedding_provider, get_provider_for_page


async def _mk_user(db, email: str) -> User:
    u = User(email=email, password_hash="x", display_name="t")
    db.add(u)
    await db.flush()
    return u


async def _set_default(db, user, provider: str):
    row = await db.get(UserLLMSettings, user.id)
    if row is None:
        row = UserLLMSettings(user_id=user.id)
        db.add(row)
    row.mode = "single"
    row.provider = provider
    await db.flush()
    return row


async def _set_mode(db, user, mode: str):
    row = await db.get(UserLLMSettings, user.id)
    row.mode = mode
    await db.flush()


async def _add_profile(db, user, role: str, provider: str):
    db.add(LLMProfile(user_id=user.id, role=role, provider=provider))
    await db.flush()


@pytest.mark.asyncio
async def test_single_mode_routes_everything_to_default():
    async with SessionLocal() as db:
        u = await _mk_user(db, "single@test.com")
        await _set_default(db, u, "openai")
        for page in ("flow.polish", "flow.extract", "story_check", "flow.companion", "llm.test"):
            prov = await get_provider_for_page(db, u, page)
            assert prov.name == "openai", page


@pytest.mark.asyncio
async def test_split_mode_routes_by_category():
    async with SessionLocal() as db:
        u = await _mk_user(db, "split@test.com")
        await _set_default(db, u, "lmstudio")
        await _set_mode(db, u, "split")
        await _add_profile(db, u, "creative", "anthropic")
        await _add_profile(db, u, "technical", "lmstudio")

        # creative pages → anthropic
        for page in ("flow.polish", "story_check", "flow.companion"):
            assert (await get_provider_for_page(db, u, page)).name == "anthropic", page
        # technical pages → lmstudio
        for page in ("flow.extract", "llm.test"):
            assert (await get_provider_for_page(db, u, page)).name == "lmstudio", page


@pytest.mark.asyncio
async def test_split_mode_falls_back_to_default_when_category_unset():
    async with SessionLocal() as db:
        u = await _mk_user(db, "split2@test.com")
        await _set_default(db, u, "openai")
        await _set_mode(db, u, "split")
        await _add_profile(db, u, "creative", "anthropic")
        # technical profile not set → falls back to default (openai)
        assert (await get_provider_for_page(db, u, "flow.extract")).name == "openai"
        assert (await get_provider_for_page(db, u, "flow.polish")).name == "anthropic"


@pytest.mark.asyncio
async def test_custom_mode_per_task_then_category_then_default():
    async with SessionLocal() as db:
        u = await _mk_user(db, "custom@test.com")
        await _set_default(db, u, "lmstudio")
        await _set_mode(db, u, "custom")
        await _add_profile(db, u, "creative", "anthropic")
        await _add_profile(db, u, "task:flow.polish", "openai")

        # exact task wins
        assert (await get_provider_for_page(db, u, "flow.polish")).name == "openai"
        # no task profile → falls back to category (creative=anthropic)
        assert (await get_provider_for_page(db, u, "flow.companion")).name == "anthropic"
        # no task, no category (technical unset) → default lmstudio
        assert (await get_provider_for_page(db, u, "flow.extract")).name == "lmstudio"


@pytest.mark.asyncio
async def test_embedding_never_anthropic():
    async with SessionLocal() as db:
        u = await _mk_user(db, "embed@test.com")
        await _set_default(db, u, "anthropic")  # default can't embed
        # no embedding profile → must fall back to a safe embed-capable provider
        prov = await get_embedding_provider(db, u)
        assert prov.name == "lmstudio"

        # explicit embedding profile is honored
        await _add_profile(db, u, "embedding", "openai")
        assert (await get_embedding_provider(db, u)).name == "openai"
