from fastapi import APIRouter

from app.core.deps import CurrentUser, DB, get_user_story
from app.core.errors import envelope_ok
from app.db.schemas import StoryCheckRequest
from app.services import story_check_service

router = APIRouter()


@router.post("/{story_id}/check")
async def run_check(story_id: str, payload: StoryCheckRequest, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    report = await story_check_service.check(db, user, story_id, payload.chapter_id, payload.pass_type)
    await db.commit()
    return envelope_ok(report.model_dump())
