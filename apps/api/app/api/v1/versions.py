from fastapi import APIRouter
from sqlalchemy import select

from app.core.deps import CurrentUser, DB, get_user_story
from app.core.errors import NotFound, envelope_ok
from app.db.models import StoryVersion
from app.services import version_service

router = APIRouter()


@router.get("/{story_id}/versions")
async def list_versions(story_id: str, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    rows = (await db.execute(
        select(StoryVersion).where(StoryVersion.story_id == story_id).order_by(StoryVersion.version_no.desc())
    )).scalars().all()
    return envelope_ok({"versions": [
        {"id": v.id, "version_no": v.version_no, "note": v.note, "created_at": v.created_at.isoformat()}
        for v in rows
    ]})


@router.get("/{story_id}/versions/{version_no}")
async def get_version(story_id: str, version_no: int, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    row = (await db.execute(
        select(StoryVersion).where(StoryVersion.story_id == story_id, StoryVersion.version_no == version_no)
    )).scalar_one_or_none()
    if row is None:
        raise NotFound("Version not found")
    return envelope_ok({"version": {"version_no": row.version_no, "snapshot": row.snapshot, "note": row.note, "created_at": row.created_at.isoformat()}})


@router.post("/{story_id}/versions")
async def create_version(story_id: str, payload: dict, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    note = (payload or {}).get("note", "manual save")
    v = await version_service.snapshot(db, story_id, note=note)
    await db.commit()
    return envelope_ok({"version": {"version_no": v.version_no, "id": v.id, "note": v.note}})
