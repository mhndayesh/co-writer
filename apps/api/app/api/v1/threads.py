from fastapi import APIRouter
from sqlalchemy import select

from app.core.deps import CurrentUser, DB, get_user_story
from app.core.errors import NotFound, envelope_ok
from app.db.models import PlotThread
from app.db.schemas import PlotThreadIn, PlotThreadOut

router = APIRouter()


@router.get("/{story_id}/threads")
async def list_threads(story_id: str, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    rows = (await db.execute(select(PlotThread).where(PlotThread.story_id == story_id))).scalars().all()
    return envelope_ok({"threads": [PlotThreadOut.model_validate(r).model_dump() for r in rows]})


@router.post("/{story_id}/threads")
async def create_thread(story_id: str, payload: PlotThreadIn, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    row = PlotThread(story_id=story_id, **payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return envelope_ok({"thread": PlotThreadOut.model_validate(row).model_dump()})


@router.patch("/{story_id}/threads/{thread_id}")
async def patch_thread(story_id: str, thread_id: str, payload: PlotThreadIn, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    row = await db.get(PlotThread, thread_id)
    if row is None or row.story_id != story_id:
        raise NotFound("Thread not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await db.commit()
    await db.refresh(row)
    return envelope_ok({"thread": PlotThreadOut.model_validate(row).model_dump()})


@router.delete("/{story_id}/threads/{thread_id}")
async def delete_thread(story_id: str, thread_id: str, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    row = await db.get(PlotThread, thread_id)
    if row is None or row.story_id != story_id:
        raise NotFound("Thread not found")
    await db.delete(row)
    await db.commit()
    return envelope_ok({"deleted": thread_id})
