"""Character Voice Studio — Narrative Observer + Dialogue Writer + Place Identity
+ post-scene evolve + voice comparison.

URL prefix /v1/stories. Avoids the /{story_id}/voice/* namespace (owned by the
existing deterministic voice-profile endpoints in narrative.py).
"""
from fastapi import APIRouter

from app.core.deps import CurrentUser, DB, get_user_story
from app.core.errors import envelope_ok
from app.db.schemas import (
    ApplyEvolveRequest,
    CompareRequest,
    EvolveRequest,
    MarkIntentionalRequest,
    ObserverCritiqueRequest,
    PlaceBuildRequest,
    PlaceIdentityOut,
    PlaceIdentityPatch,
    RewriteRequest,
    UpdateProfileFromNoteRequest,
)
from app.db.schemas import IdentityOut
from app.services import observer_service
from app.services.identity_questions import PLACE_BANK

router = APIRouter()


# ── Place Identity (Part 1C) ────────────────────────────────────────────────────

@router.get("/{story_id}/place/questions")
async def place_questions(story_id: str, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    return envelope_ok({"questions": PLACE_BANK})


@router.get("/{story_id}/place/{location_id}")
async def get_place(story_id: str, location_id: str, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    place = await observer_service.get_place_identity(db, story_id, location_id)
    await db.commit()
    return envelope_ok({"place": PlaceIdentityOut.model_validate(place).model_dump()})


@router.patch("/{story_id}/place/{location_id}")
async def patch_place(story_id: str, location_id: str, payload: PlaceIdentityPatch, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    place = await observer_service.patch_place_identity(db, story_id, location_id, payload.model_dump(exclude_unset=True))
    await db.commit()
    return envelope_ok({"place": PlaceIdentityOut.model_validate(place).model_dump()})


@router.post("/{story_id}/place/{location_id}/build")
async def build_place(story_id: str, location_id: str, payload: PlaceBuildRequest, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    place = await observer_service.build_place(db, user, story_id, location_id, payload.answers)
    await db.commit()
    return envelope_ok({"place": PlaceIdentityOut.model_validate(place).model_dump()})


# ── Narrative Observer + Dialogue Writer ────────────────────────────────────────

@router.post("/{story_id}/observer/critique")
async def critique(story_id: str, payload: ObserverCritiqueRequest, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    result = await observer_service.observe(db, user, story_id, payload.draft, payload.strictness, payload.chapter_id)
    await db.commit()
    return envelope_ok(result)


@router.post("/{story_id}/observer/rewrite")
async def rewrite(story_id: str, payload: RewriteRequest, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    result = await observer_service.rewrite(db, user, story_id, payload.model_dump())
    await db.commit()
    return envelope_ok(result)


@router.post("/{story_id}/observer/mark-intentional")
async def mark_intentional(story_id: str, payload: MarkIntentionalRequest, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    eid = await observer_service.mark_intentional(db, story_id, payload.model_dump())
    await db.commit()
    return envelope_ok({"exception_id": eid})


@router.post("/{story_id}/observer/update-profile")
async def update_profile(story_id: str, payload: UpdateProfileFromNoteRequest, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    identity = await observer_service.update_profile_from_note(db, story_id, payload.model_dump())
    await db.commit()
    return envelope_ok({"identity": IdentityOut.model_validate(identity).model_dump()})


# ── Post-scene evolve ───────────────────────────────────────────────────────────

@router.post("/{story_id}/identity/evolve")
async def evolve(story_id: str, payload: EvolveRequest, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    result = await observer_service.evolve_suggestions(db, user, story_id, payload.text, payload.chapter_id)
    await db.commit()
    return envelope_ok(result)


@router.post("/{story_id}/identity/evolve/apply")
async def apply_evolution(story_id: str, payload: ApplyEvolveRequest, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    applied = await observer_service.apply_evolution(db, story_id, [d.model_dump() for d in payload.decisions])
    await db.commit()
    return envelope_ok({"applied": applied})


# ── Voice comparison ────────────────────────────────────────────────────────────

@router.post("/{story_id}/identity/compare")
async def compare(story_id: str, payload: CompareRequest, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    result = await observer_service.compare_voices(db, user, story_id, payload.character_ids, payload.situation)
    await db.commit()
    return envelope_ok(result)
