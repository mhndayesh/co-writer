from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import select

from app.core.deps import CurrentUser, DB
from app.core.errors import envelope_ok
from app.core.security import encrypt_secret
from app.db.models import LLMProfile, UserLLMSettings
from app.db.schemas import (
    LLMConfigIn,
    LLMConfigOut,
    LLMProfileOut,
    LLMSettingsIn,
    LLMSettingsOut,
    LLMStatus,
)
from app.services.llm.factory import (
    _from_default,
    _from_profile,
    get_provider_for_page,
    get_provider_for_user,
)
from app.services.llm.roles import CREATIVE, CUSTOM_TASKS, EMBEDDING, TECHNICAL

router = APIRouter()


# ── helpers ─────────────────────────────────────────────────────────────

def _settings_out(row: UserLLMSettings | None) -> LLMSettingsOut:
    if row is None:
        from app.core.config import get_settings as _gs
        s = _gs()
        return LLMSettingsOut(
            provider=s.llm_provider,
            base_url=s.lmstudio_base_url if s.llm_provider == "lmstudio" else "",
            model="", embed_model="", has_api_key=False,
        )
    return LLMSettingsOut(
        provider=row.provider, base_url=row.base_url, model=row.model,
        embed_model=row.embed_model, has_api_key=bool(row.api_key_ciphertext),
    )


def _profile_out_from_default(row: UserLLMSettings | None) -> LLMProfileOut:
    if row is None:
        from app.core.config import get_settings as _gs
        s = _gs()
        return LLMProfileOut(provider=s.llm_provider, base_url="", model="", embed_model="", has_api_key=False)
    return LLMProfileOut(
        provider=row.provider, base_url=row.base_url, model=row.model,
        embed_model=row.embed_model, has_api_key=bool(row.api_key_ciphertext),
    )


def _profile_out(prof: LLMProfile) -> LLMProfileOut:
    return LLMProfileOut(
        provider=prof.provider, base_url=prof.base_url, model=prof.model,
        embed_model=prof.embed_model, has_api_key=bool(prof.api_key_ciphertext),
    )


async def _upsert_default(db, user, payload, *, mode: str | None = None) -> UserLLMSettings:
    row = await db.get(UserLLMSettings, user.id)
    if row is None:
        row = UserLLMSettings(user_id=user.id)
        db.add(row)
    if mode is not None:
        row.mode = mode
    if payload is not None:
        row.provider = payload.provider
        row.base_url = payload.base_url
        row.model = payload.model
        row.embed_model = payload.embed_model
        if payload.api_key:
            row.api_key_ciphertext = encrypt_secret(payload.api_key)
    row.updated_at = datetime.now(timezone.utc)
    return row


async def _upsert_profile(db, user, role: str, payload) -> None:
    prof = (await db.execute(
        select(LLMProfile).where(LLMProfile.user_id == user.id, LLMProfile.role == role)
    )).scalar_one_or_none()
    if prof is None:
        prof = LLMProfile(user_id=user.id, role=role)
        db.add(prof)
    prof.provider = payload.provider
    prof.base_url = payload.base_url
    prof.model = payload.model
    prof.embed_model = payload.embed_model
    if payload.api_key:
        prof.api_key_ciphertext = encrypt_secret(payload.api_key)
    prof.updated_at = datetime.now(timezone.utc)


# ── legacy single-profile endpoints (kept for back-compat) ───────────────

@router.get("/settings")
async def get_settings_endpoint(user: CurrentUser, db: DB):
    row = await db.get(UserLLMSettings, user.id)
    return envelope_ok(_settings_out(row).model_dump())


@router.put("/settings")
async def put_settings(payload: LLMSettingsIn, user: CurrentUser, db: DB):
    row = await _upsert_default(db, user, payload)
    await db.commit()
    await db.refresh(row)
    return envelope_ok(_settings_out(row).model_dump())


# ── structured multi-profile config ──────────────────────────────────────

@router.get("/config")
async def get_config(user: CurrentUser, db: DB):
    row = await db.get(UserLLMSettings, user.id)
    profiles = (await db.execute(
        select(LLMProfile).where(LLMProfile.user_id == user.id)
    )).scalars().all()
    by_role = {p.role: p for p in profiles}

    tasks = {
        role[len("task:"):]: _profile_out(p)
        for role, p in by_role.items() if role.startswith("task:")
    }
    out = LLMConfigOut(
        mode=(row.mode if row and row.mode in ("single", "split", "custom") else "single"),
        default=_profile_out_from_default(row),
        creative=_profile_out(by_role[CREATIVE]) if CREATIVE in by_role else None,
        technical=_profile_out(by_role[TECHNICAL]) if TECHNICAL in by_role else None,
        embedding=_profile_out(by_role[EMBEDDING]) if EMBEDDING in by_role else None,
        tasks=tasks,
    )
    return envelope_ok(out.model_dump())


@router.put("/config")
async def put_config(payload: LLMConfigIn, user: CurrentUser, db: DB):
    await _upsert_default(db, user, payload.default, mode=payload.mode)
    if payload.creative is not None:
        await _upsert_profile(db, user, CREATIVE, payload.creative)
    if payload.technical is not None:
        await _upsert_profile(db, user, TECHNICAL, payload.technical)
    if payload.embedding is not None:
        await _upsert_profile(db, user, EMBEDDING, payload.embedding)
    for page, prof in (payload.tasks or {}).items():
        await _upsert_profile(db, user, f"task:{page}", prof)
    await db.commit()
    return await get_config(user, db)


# ── status (per active role) + test ──────────────────────────────────────

async def _status_for(provider, role: str) -> LLMStatus:
    ok, detail = await provider.ping()
    return LLMStatus(provider=provider.name, model=provider.default_model, reachable=ok, detail=detail, role=role)


@router.get("/status")
async def status(user: CurrentUser, db: DB):
    """Return reachability for every active role under the current mode."""
    row = await db.get(UserLLMSettings, user.id)
    mode = (row.mode if row else "single") or "single"
    statuses: list[dict] = []

    if mode == "single":
        prov = await get_provider_for_user(db, user)
        statuses.append((await _status_for(prov, "default")).model_dump())
    else:
        # One representative page per category drives resolution.
        prov_c = await get_provider_for_page(db, user, "flow.polish")
        statuses.append((await _status_for(prov_c, "creative")).model_dump())
        prov_t = await get_provider_for_page(db, user, "flow.extract")
        statuses.append((await _status_for(prov_t, "technical")).model_dump())
        from app.services.llm.factory import get_embedding_provider
        prov_e = await get_embedding_provider(db, user)
        statuses.append((await _status_for(prov_e, "embedding")).model_dump())

    # Keep a flat top-level field for the legacy sidebar pill (first status).
    primary = statuses[0]
    return envelope_ok({**primary, "statuses": statuses})


@router.post("/test")
async def test(payload: dict, user: CurrentUser, db: DB):
    """Test a profile. payload may include `page` (route via category) or
    `role` ("default"|"creative"|"technical"|"embedding"|"task:<page>")."""
    from app.services import llm_service

    payload = payload or {}
    prompt = payload.get("prompt", "Say hello in one short sentence.")
    page = payload.get("page") or payload.get("role") or "llm.test"

    # Embeddings can't chat — ping the embedding provider instead.
    if page == "embedding":
        from app.services.llm.factory import get_embedding_provider
        prov = await get_embedding_provider(db, user)
        ok, detail = await prov.ping()
        return envelope_ok({"text": f"Embedding provider {prov.name}: {'ok' if ok else detail}", "model": prov.default_embed_model, "fallback": False})

    # Map a bare role to a representative page so run()'s router picks it up.
    role_to_page = {"creative": "flow.polish", "technical": "flow.extract", "default": "llm.test"}
    if page in role_to_page:
        page = role_to_page[page]
    elif page.startswith("task:"):
        page = page[len("task:"):]

    resp, fallback = await llm_service.run(
        db, user, page=page,
        system="You are a helpful assistant. Reply briefly.",
        user_msg=prompt, max_tokens=200,
    )
    await db.commit()
    return envelope_ok({"text": resp.text, "model": resp.model, "fallback": fallback})
