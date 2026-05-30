from fastapi import APIRouter
from sqlalchemy import select

from app.core.deps import CurrentUser, DB, get_user_story
from app.core.errors import NotFound, envelope_ok
from app.db.models import SceneCard
from app.db.schemas import SceneCardIn, SceneCardOut

router = APIRouter()


@router.get("/{story_id}/scenes")
async def list_scenes(story_id: str, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    rows = (await db.execute(select(SceneCard).where(SceneCard.story_id == story_id).order_by(SceneCard.ordinal))).scalars().all()
    return envelope_ok({"scenes": [SceneCardOut.model_validate(r).model_dump() for r in rows]})


@router.post("/{story_id}/scenes")
async def create_scene(story_id: str, payload: SceneCardIn, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    row = SceneCard(story_id=story_id, **payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return envelope_ok({"scene": SceneCardOut.model_validate(row).model_dump()})


@router.patch("/{story_id}/scenes/{scene_id}")
async def patch_scene(story_id: str, scene_id: str, payload: SceneCardIn, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    row = await db.get(SceneCard, scene_id)
    if row is None or row.story_id != story_id:
        raise NotFound("Scene not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await db.commit()
    await db.refresh(row)
    return envelope_ok({"scene": SceneCardOut.model_validate(row).model_dump()})


@router.delete("/{story_id}/scenes/{scene_id}")
async def delete_scene(story_id: str, scene_id: str, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    row = await db.get(SceneCard, scene_id)
    if row is None or row.story_id != story_id:
        raise NotFound("Scene not found")
    await db.delete(row)
    await db.commit()
    return envelope_ok({"deleted": scene_id})
