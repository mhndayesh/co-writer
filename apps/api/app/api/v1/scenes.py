from fastapi import APIRouter, Query
from sqlalchemy import delete as sa_delete, select

from app.core.deps import CurrentUser, DB, get_user_story
from app.core.errors import NotFound, envelope_ok
from app.db.models import PlotThreadSceneLink, SceneCard
from app.db.schemas import SceneCardIn, SceneCardOut, SceneCardPatch

router = APIRouter()


async def _sync_thread_links(db: DB, story_id: str, scene: SceneCard) -> None:
    await db.execute(sa_delete(PlotThreadSceneLink).where(PlotThreadSceneLink.scene_id == scene.id))
    for thread_id in scene.plot_thread_ids or []:
        db.add(PlotThreadSceneLink(
            story_id=story_id,
            thread_id=thread_id,
            scene_id=scene.id,
            chapter_id=scene.chapter_id,
            status="touch",
            strength=1.0,
            evidence=scene.summary or scene.beat or scene.title,
        ))


@router.get("/{story_id}/scenes")
async def list_scenes(
    story_id: str,
    user: CurrentUser,
    db: DB,
    limit: int | None = Query(None, ge=1, le=500, description="Opt-in page size; omit to return all."),
    offset: int = Query(0, ge=0),
):
    await get_user_story(story_id, user, db)
    stmt = select(SceneCard).where(SceneCard.story_id == story_id).order_by(SceneCard.chapter_id, SceneCard.ordinal)
    if limit is not None:
        stmt = stmt.offset(offset).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return envelope_ok({"scenes": [SceneCardOut.model_validate(r).model_dump() for r in rows]})


@router.post("/{story_id}/scenes")
async def create_scene(story_id: str, payload: SceneCardIn, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    row = SceneCard(story_id=story_id, **payload.model_dump())
    db.add(row)
    await db.flush()
    await _sync_thread_links(db, story_id, row)
    await db.commit()
    await db.refresh(row)
    return envelope_ok({"scene": SceneCardOut.model_validate(row).model_dump()})


@router.patch("/{story_id}/scenes/{scene_id}")
async def patch_scene(story_id: str, scene_id: str, payload: SceneCardPatch, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    row = await db.get(SceneCard, scene_id)
    if row is None or row.story_id != story_id:
        raise NotFound("Scene not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    if "plot_thread_ids" in payload.model_fields_set:
        await _sync_thread_links(db, story_id, row)
    await db.commit()
    await db.refresh(row)
    return envelope_ok({"scene": SceneCardOut.model_validate(row).model_dump()})


@router.delete("/{story_id}/scenes/{scene_id}")
async def delete_scene(story_id: str, scene_id: str, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    row = await db.get(SceneCard, scene_id)
    if row is None or row.story_id != story_id:
        raise NotFound("Scene not found")
    await db.execute(sa_delete(PlotThreadSceneLink).where(PlotThreadSceneLink.scene_id == scene_id))
    await db.delete(row)
    await db.commit()
    return envelope_ok({"deleted": scene_id})
