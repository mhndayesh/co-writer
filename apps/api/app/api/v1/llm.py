from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy.orm.attributes import flag_modified

from app.core.deps import CurrentUser, DB
from app.core.errors import envelope_ok
from app.core.security import encrypt_secret
from app.db.models import UserLLMSettings
from app.db.schemas import (
    LaneConfigOut,
    LLMConfigIn,
    LLMConfigOut,
    LLMStatus,
    ProviderInfo,
)
from app.services.llm import factory
from app.services.llm.presets import PRESETS
from app.services.llm.roles import EMBEDDING, LANES_ORDER

router = APIRouter()


# ── helpers ─────────────────────────────────────────────────────────────

def _default_lane() -> dict:
    return factory.default_lane_config()


def _lanes(row: UserLLMSettings | None) -> dict:
    lanes = dict((row.lanes if row and row.lanes else {}) or {})
    d = _default_lane()
    for lane in ("creative", "technical", "embedding"):
        lanes.setdefault(lane, dict(d))
    return lanes


def _lane_out(cfg: dict) -> LaneConfigOut:
    return LaneConfigOut(
        provider=cfg.get("provider", ""),
        base_url=cfg.get("base_url", ""),
        model=cfg.get("model", ""),
        embed_model=cfg.get("embed_model", ""),
        has_api_key=bool(cfg.get("api_key_ciphertext")),
    )


def _config_out(row: UserLLMSettings | None) -> LLMConfigOut:
    lanes = _lanes(row)
    return LLMConfigOut(
        creative=_lane_out(lanes["creative"]),
        technical=_lane_out(lanes["technical"]),
        embedding=_lane_out(lanes["embedding"]),
    )


def _apply_lane(existing: dict, incoming) -> dict:
    """Merge an incoming LaneConfigIn into the stored lane dict.
    Blank api_key preserves the existing ciphertext."""
    out = {
        "provider": incoming.provider,
        "base_url": incoming.base_url,
        "model": incoming.model,
        "embed_model": incoming.embed_model,
        "api_key_ciphertext": existing.get("api_key_ciphertext", ""),
    }
    if incoming.api_key:
        out["api_key_ciphertext"] = encrypt_secret(incoming.api_key)
    return out


# ── config ───────────────────────────────────────────────────────────────

@router.get("/config")
async def get_config(user: CurrentUser, db: DB):
    row = await db.get(UserLLMSettings, user.id)
    return envelope_ok(_config_out(row).model_dump())


@router.put("/config")
async def put_config(payload: LLMConfigIn, user: CurrentUser, db: DB):
    row = await db.get(UserLLMSettings, user.id)
    if row is None:
        row = UserLLMSettings(user_id=user.id, lanes={})
        db.add(row)
    lanes = _lanes(row)
    for lane, incoming in (
        ("creative", payload.creative),
        ("technical", payload.technical),
        ("embedding", payload.embedding),
    ):
        if incoming is not None:
            lanes[lane] = _apply_lane(lanes.get(lane, {}), incoming)
    row.lanes = lanes
    row.updated_at = datetime.now(timezone.utc)
    # JSON mutated-in-place needs an explicit flag for SQLAlchemy to persist it.
    flag_modified(row, "lanes")
    await db.commit()
    await db.refresh(row)
    return envelope_ok(_config_out(row).model_dump())


# ── providers (preset metadata for the frontend) ──────────────────────────

@router.get("/providers")
async def providers():
    out = [
        ProviderInfo(
            name=p.name, base_url=p.base_url, default_model=p.default_model,
            default_embed_model=p.default_embed_model, can_embed=p.can_embed,
        ).model_dump()
        for p in PRESETS.values()
    ]
    return envelope_ok({"providers": out})


# ── status + test ─────────────────────────────────────────────────────────

@router.get("/status")
async def status(user: CurrentUser, db: DB):
    """Reachability per lane."""
    statuses: list[dict] = []
    representative = {"creative": "flow.polish", "technical": "flow.extract"}
    for lane in LANES_ORDER:
        if lane == EMBEDDING:
            prov = await factory.get_embedding_provider(db, user)
        else:
            prov = await factory.get_provider_for_page(db, user, representative[lane])
        ok, detail = await prov.ping()
        statuses.append(
            LLMStatus(
                provider=prov.name,
                model=prov.default_model,
                reachable=ok,
                detail=detail,
                lane=lane,
            ).model_dump()
        )
    primary = statuses[0] if statuses else {
        "provider": "",
        "model": "",
        "reachable": False,
        "detail": "no config",
        "lane": "creative",
    }
    return envelope_ok({**primary, "statuses": statuses})


@router.post("/test")
async def test(payload: dict, user: CurrentUser, db: DB):
    """Test a lane. payload: {lane: creative|technical|embedding, prompt?}."""
    from app.services import llm_service

    payload = payload or {}
    lane = payload.get("lane", "creative")
    prompt = payload.get("prompt", "Say hello in one short sentence.")

    if lane == "embedding":
        prov = await factory.get_embedding_provider(db, user)
        ok, detail = await prov.ping()
        return envelope_ok({
            "text": f"Embedding provider {prov.name}: {'ok' if ok else detail}",
            "model": prov.default_embed_model,
            "fallback": not ok,
        })

    page = "flow.extract" if lane == "technical" else "flow.polish"
    resp, fallback = await llm_service.run(
        db,
        user,
        page=page,
        system="You are a helpful assistant. Reply briefly.",
        user_msg=prompt,
        max_tokens=200,
    )
    await db.commit()
    return envelope_ok({"text": resp.text, "model": resp.model, "fallback": fallback})
