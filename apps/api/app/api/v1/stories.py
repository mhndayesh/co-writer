from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.core.deps import CurrentUser, DB, get_user_story
from app.core.errors import envelope_ok
from app.db.models import Chapter, Character, Story, World
from app.db.schemas import StoryCreate, StoryOut, StoryStats, StoryUpdate

router = APIRouter()


async def _story_out(db, story: Story) -> dict:
    chapter_count = await db.scalar(select(func.count()).where(Chapter.story_id == story.id)) or 0
    character_count = await db.scalar(select(func.count()).where(Character.story_id == story.id)) or 0
    word_count = await db.scalar(select(func.coalesce(func.sum(func.length(Chapter.content)), 0)).where(Chapter.story_id == story.id)) or 0
    # cheap word approximation: bytes / 5
    words = int(word_count) // 5
    return {
        **StoryOut.model_validate(story).model_dump(mode="json"),
        "stats": StoryStats(words=words, chapters=int(chapter_count), characters=int(character_count)).model_dump(),
    }


@router.get("")
async def list_stories(
    user: CurrentUser,
    db: DB,
    limit: int | None = Query(None, ge=1, le=200, description="Opt-in page size; omit to return all."),
    offset: int = Query(0, ge=0),
):
    stmt = select(Story).where(Story.user_id == user.id).order_by(Story.updated_at.desc())
    if limit is not None:
        stmt = stmt.offset(offset).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    out = [await _story_out(db, s) for s in rows]
    return envelope_ok({"stories": out})


@router.post("")
async def create_story(payload: StoryCreate, user: CurrentUser, db: DB):
    story = Story(
        user_id=user.id,
        title=payload.title or "Untitled",
        genre=payload.genre,
        palette_idx=payload.palette_idx,
    )
    db.add(story)
    await db.flush()
    db.add(World(story_id=story.id, title=story.title, genre=story.genre))
    await db.commit()
    await db.refresh(story)
    return envelope_ok({"story": await _story_out(db, story)})


@router.get("/{story_id}")
async def get_story(story_id: str, user: CurrentUser, db: DB):
    story = await get_user_story(story_id, user, db)
    return envelope_ok({"story": await _story_out(db, story)})


@router.patch("/{story_id}")
async def update_story(story_id: str, payload: StoryUpdate, user: CurrentUser, db: DB):
    story = await get_user_story(story_id, user, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(story, field, value)
    await db.commit()
    await db.refresh(story)
    return envelope_ok({"story": await _story_out(db, story)})


@router.delete("/{story_id}")
async def delete_story(story_id: str, user: CurrentUser, db: DB):
    story = await get_user_story(story_id, user, db)
    await db.delete(story)
    await db.commit()
    return envelope_ok({"deleted": story_id})
