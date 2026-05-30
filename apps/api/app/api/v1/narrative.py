from fastapi import APIRouter, Query

from app.core.deps import CurrentUser, DB, get_user_story
from app.core.errors import NotFound, envelope_ok
from app.db.models import Chapter, Revelation, SceneCard
from app.db.schemas import (
    CharacterVoiceProfileOut,
    RevelationIn,
    RevelationOut,
    RevelationPatch,
)
from app.services import narrative_service, voice_service

router = APIRouter()


async def _validate_revelation_refs(db: DB, story_id: str, payload: RevelationIn | RevelationPatch) -> None:
    if payload.scene_id:
        scene = await db.get(SceneCard, payload.scene_id)
        if scene is None or scene.story_id != story_id:
            raise NotFound("Scene not found")
    if payload.chapter_id:
        chapter = await db.get(Chapter, payload.chapter_id)
        if chapter is None or chapter.story_id != story_id:
            raise NotFound("Chapter not found")


@router.get("/{story_id}/timeline")
async def get_timeline(
    story_id: str,
    user: CurrentUser,
    db: DB,
    order: str = Query("story", pattern="^(story|reading)$"),
):
    await get_user_story(story_id, user, db)
    scenes = await narrative_service.timeline(db, story_id, order=order)
    return envelope_ok({"scenes": [s.model_dump() for s in scenes]})


@router.get("/{story_id}/weave")
async def get_weave(story_id: str, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    return envelope_ok((await narrative_service.weave(db, story_id)).model_dump())


@router.get("/{story_id}/revelations")
async def list_revelations(story_id: str, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    rows = await narrative_service.list_revelations(db, story_id)
    return envelope_ok({"revelations": [RevelationOut.model_validate(r).model_dump() for r in rows]})


@router.post("/{story_id}/revelations")
async def create_revelation(story_id: str, payload: RevelationIn, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    await _validate_revelation_refs(db, story_id, payload)
    row = Revelation(story_id=story_id, **payload.model_dump())
    if row.chapter_id is None and row.scene_id:
        scene = await db.get(SceneCard, row.scene_id)
        row.chapter_id = scene.chapter_id if scene else None
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return envelope_ok({"revelation": RevelationOut.model_validate(row).model_dump()})


@router.patch("/{story_id}/revelations/{revelation_id}")
async def patch_revelation(story_id: str, revelation_id: str, payload: RevelationPatch, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    await _validate_revelation_refs(db, story_id, payload)
    row = await db.get(Revelation, revelation_id)
    if row is None or row.story_id != story_id:
        raise NotFound("Revelation not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    if row.chapter_id is None and row.scene_id:
        scene = await db.get(SceneCard, row.scene_id)
        row.chapter_id = scene.chapter_id if scene else None
    await db.commit()
    await db.refresh(row)
    return envelope_ok({"revelation": RevelationOut.model_validate(row).model_dump()})


@router.delete("/{story_id}/revelations/{revelation_id}")
async def delete_revelation(story_id: str, revelation_id: str, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    row = await db.get(Revelation, revelation_id)
    if row is None or row.story_id != story_id:
        raise NotFound("Revelation not found")
    await db.delete(row)
    await db.commit()
    return envelope_ok({"deleted": revelation_id})


@router.get("/{story_id}/voice")
async def list_voice_profiles(story_id: str, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    rows = await voice_service.list_profiles(db, story_id)
    await db.commit()
    return envelope_ok({"profiles": [CharacterVoiceProfileOut.model_validate(r).model_dump() for r in rows]})


@router.post("/{story_id}/voice/rebuild")
async def rebuild_voice_profiles(story_id: str, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    rows = await voice_service.rebuild_profiles(db, story_id)
    await db.commit()
    return envelope_ok({"profiles": [CharacterVoiceProfileOut.model_validate(r).model_dump() for r in rows]})
