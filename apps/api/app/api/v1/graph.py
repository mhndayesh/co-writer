from fastapi import APIRouter

from app.core.deps import CurrentUser, DB, get_user_story
from app.core.errors import envelope_ok
from app.services import graph_service

router = APIRouter()


@router.get("/{story_id}/graph/view")
async def view(story_id: str, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    view = await graph_service.get_view(db, story_id)
    return envelope_ok(view.model_dump())


@router.post("/{story_id}/graph/reproject")
async def reproject(story_id: str, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    res = await graph_service.reproject_story(db, story_id)
    await db.commit()
    return envelope_ok(res)
