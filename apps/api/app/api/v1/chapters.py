from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.core.deps import CurrentUser, DB, get_user_story
from app.core.errors import NotFound, envelope_ok
from app.db.models import Chapter
from app.db.schemas import ChapterIn, ChapterOut, ChapterPatch

router = APIRouter()


@router.get("/{story_id}/chapters")
async def list_chapters(
    story_id: str,
    user: CurrentUser,
    db: DB,
    limit: int | None = Query(None, ge=1, le=500, description="Opt-in page size; omit to return all."),
    offset: int = Query(0, ge=0),
):
    await get_user_story(story_id, user, db)
    stmt = select(Chapter).where(Chapter.story_id == story_id).order_by(Chapter.number)
    if limit is not None:
        stmt = stmt.offset(offset).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return envelope_ok({"chapters": [ChapterOut.model_validate(c).model_dump(mode="json") for c in rows]})


@router.post("/{story_id}/chapters")
async def create_chapter(story_id: str, payload: ChapterIn, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    next_number = payload.number
    if next_number is None:
        max_num = await db.scalar(select(func.coalesce(func.max(Chapter.number), 0)).where(Chapter.story_id == story_id)) or 0
        next_number = int(max_num) + 1
    chapter = Chapter(story_id=story_id, **{**payload.model_dump(exclude={"number"}), "number": next_number})
    db.add(chapter)
    await db.commit()
    await db.refresh(chapter)
    return envelope_ok({"chapter": ChapterOut.model_validate(chapter).model_dump(mode="json")})


@router.get("/{story_id}/chapters/{chapter_id}")
async def get_chapter(story_id: str, chapter_id: str, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    chapter = await db.get(Chapter, chapter_id)
    if chapter is None or chapter.story_id != story_id:
        raise NotFound("Chapter not found")
    return envelope_ok({"chapter": ChapterOut.model_validate(chapter).model_dump(mode="json")})


@router.patch("/{story_id}/chapters/{chapter_id}")
async def patch_chapter(story_id: str, chapter_id: str, payload: ChapterPatch, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    chapter = await db.get(Chapter, chapter_id)
    if chapter is None or chapter.story_id != story_id:
        raise NotFound("Chapter not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(chapter, field, value)
    await db.commit()
    await db.refresh(chapter)
    return envelope_ok({"chapter": ChapterOut.model_validate(chapter).model_dump(mode="json")})


@router.delete("/{story_id}/chapters/{chapter_id}")
async def delete_chapter(story_id: str, chapter_id: str, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    chapter = await db.get(Chapter, chapter_id)
    if chapter is None or chapter.story_id != story_id:
        raise NotFound("Chapter not found")
    await db.delete(chapter)
    # Leave the gap in chapter numbering so the writer can deliberately
    # fill it back in via Flow Writing (the Flow page detects gaps and
    # defaults to targeting the lowest one).
    await db.commit()
    return envelope_ok({"deleted": chapter_id})
