"""Character Voice Studio — identity routes (the 5 layers, masks, states, history).

URL prefix /v1/stories. NOTE: we deliberately avoid the /{story_id}/voice/*
namespace — that belongs to the existing deterministic voice-profile endpoints in
narrative.py. The Voice Studio backend lives under /identity, /place, /observer.
"""
from fastapi import APIRouter

from app.core.deps import CurrentUser, DB, get_user_story
from app.core.errors import envelope_ok
from app.db.schemas import (
    AnalyzeWritingRequest,
    ApproveTraitsRequest,
    IdentityLayerPatch,
    IdentityOut,
    IdentityVersionOut,
    InterviewSubmitRequest,
    MaskIn,
    MaskOut,
    StateIn,
    StateOut,
)
from app.services import identity_service
from app.services.identity_questions import interview_for_tier

router = APIRouter()


# NOTE: this literal route MUST be declared before "/{story_id}/identity/{character_id}"
# or FastAPI would match "interview" as a character_id.
@router.get("/{story_id}/identity/interview")
async def get_interview(story_id: str, user: CurrentUser, db: DB, tier: str = "quick"):
    await get_user_story(story_id, user, db)
    return envelope_ok({"tier": tier, "questions": interview_for_tier(tier)})


@router.get("/{story_id}/identity/{character_id}")
async def get_identity(story_id: str, character_id: str, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    identity = await identity_service.get_identity(db, story_id, character_id)
    masks = await identity_service.list_masks(db, story_id, character_id)
    states = await identity_service.list_states(db, story_id, character_id)
    await db.commit()
    return envelope_ok({
        "identity": IdentityOut.model_validate(identity).model_dump(),
        "masks": [MaskOut.model_validate(m).model_dump() for m in masks],
        "states": [StateOut.model_validate(s).model_dump() for s in states],
    })


@router.patch("/{story_id}/identity/{character_id}/layer/{layer}")
async def patch_layer(
    story_id: str, character_id: str, layer: str, payload: IdentityLayerPatch, user: CurrentUser, db: DB
):
    await get_user_story(story_id, user, db)
    identity = await identity_service.patch_layer(
        db, story_id, character_id, layer, payload.payload, build_method=payload.build_method
    )
    await db.commit()
    return envelope_ok({"identity": IdentityOut.model_validate(identity).model_dump()})


# ── Method 1: analyze existing writing ─────────────────────────────────────────

@router.post("/{story_id}/identity/{character_id}/analyze")
async def analyze_writing(story_id: str, character_id: str, payload: AnalyzeWritingRequest, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    result = await identity_service.analyze_writing(
        db, user, story_id, character_id, payload.text, payload.chapter_ids
    )
    await db.commit()
    return envelope_ok(result)


@router.post("/{story_id}/identity/{character_id}/analyze/approve")
async def approve_traits(story_id: str, character_id: str, payload: ApproveTraitsRequest, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    decisions = [d.model_dump() for d in payload.decisions]
    identity = await identity_service.approve_traits(db, story_id, character_id, decisions)
    await db.commit()
    return envelope_ok({"identity": IdentityOut.model_validate(identity).model_dump()})


# ── Method 2: guided interview (GET questions route is declared at top) ────────

@router.post("/{story_id}/identity/{character_id}/interview")
async def submit_interview(story_id: str, character_id: str, payload: InterviewSubmitRequest, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    identity = await identity_service.synthesize_from_interview(
        db, user, story_id, character_id, payload.answers, payload.tier
    )
    await db.commit()
    return envelope_ok({"identity": IdentityOut.model_validate(identity).model_dump()})


# ── Relationship masks (layer 4) ───────────────────────────────────────────────

@router.get("/{story_id}/identity/{character_id}/masks")
async def list_masks(story_id: str, character_id: str, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    masks = await identity_service.list_masks(db, story_id, character_id)
    return envelope_ok({"masks": [MaskOut.model_validate(m).model_dump() for m in masks]})


@router.post("/{story_id}/identity/{character_id}/masks")
async def add_mask(story_id: str, character_id: str, payload: MaskIn, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    mask = await identity_service.add_mask(db, story_id, character_id, payload.model_dump())
    await db.commit()
    return envelope_ok({"mask": MaskOut.model_validate(mask).model_dump()})


@router.patch("/{story_id}/identity/masks/{mask_id}")
async def patch_mask(story_id: str, mask_id: str, payload: MaskIn, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    mask = await identity_service.patch_mask(db, story_id, mask_id, payload.model_dump(exclude_unset=True))
    await db.commit()
    return envelope_ok({"mask": MaskOut.model_validate(mask).model_dump()})


@router.delete("/{story_id}/identity/masks/{mask_id}")
async def delete_mask(story_id: str, mask_id: str, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    await identity_service.delete_mask(db, story_id, mask_id)
    await db.commit()
    return envelope_ok({"deleted": mask_id})


# ── Current state (layer 5) ────────────────────────────────────────────────────

@router.get("/{story_id}/identity/{character_id}/states")
async def list_states(story_id: str, character_id: str, user: CurrentUser, db: DB, active_only: bool = False):
    await get_user_story(story_id, user, db)
    states = await identity_service.list_states(db, story_id, character_id, active_only=active_only)
    return envelope_ok({"states": [StateOut.model_validate(s).model_dump() for s in states]})


@router.post("/{story_id}/identity/{character_id}/states")
async def set_state(story_id: str, character_id: str, payload: StateIn, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    state = await identity_service.set_state(db, story_id, character_id, payload.model_dump())
    await db.commit()
    return envelope_ok({"state": StateOut.model_validate(state).model_dump()})


@router.delete("/{story_id}/identity/states/{state_id}")
async def clear_state(story_id: str, state_id: str, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    await identity_service.clear_state(db, story_id, state_id)
    await db.commit()
    return envelope_ok({"cleared": state_id})


# ── Versions / arc progression ─────────────────────────────────────────────────

@router.get("/{story_id}/identity/{character_id}/versions")
async def list_versions(story_id: str, character_id: str, user: CurrentUser, db: DB, kind: str | None = None):
    await get_user_story(story_id, user, db)
    rows = await identity_service.list_versions(db, story_id, character_id, kind=kind)
    return envelope_ok({"versions": [IdentityVersionOut.model_validate(v).model_dump() for v in rows]})


@router.get("/{story_id}/identity/{character_id}/arc")
async def get_arc(story_id: str, character_id: str, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    rows = await identity_service.arc_timeline(db, story_id, character_id)
    return envelope_ok({"arc": [IdentityVersionOut.model_validate(v).model_dump() for v in rows]})
