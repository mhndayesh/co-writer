from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_optional_user, get_db
from app.core.errors import envelope_ok, Unauthorized
from app.db.models import User
from app.db.publishing_schemas import ProgressUpdate
from app.services import reader_service as rsvc

reader_router = APIRouter()


@reader_router.get("/")
async def discovery_feed(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    genre: Optional[str] = Query(None),
    sort: str = Query("recent"),
    q: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    feed = await rsvc.get_discovery_feed(db, page=page, per_page=per_page,
                                         genre=genre, sort=sort, search=q)
    return envelope_ok(feed)


@reader_router.get("/genres")
async def list_genres(db: AsyncSession = Depends(get_db)):
    return envelope_ok(list(rsvc.VALID_GENRES))


@reader_router.get("/my/library")
async def my_library(
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        return envelope_ok({"in_progress": [], "completed": [], "following": []})
    library = await rsvc.get_reader_library(user.id, db)
    return envelope_ok(library)


@reader_router.get("/{slug}")
async def story_landing(
    slug: str,
    db: AsyncSession = Depends(get_db),
):
    data = await rsvc.get_story_landing(slug, db)
    # get_story_landing flushes a view_count++ but get_db never auto-commits, so
    # without this the increment rolls back on session close — the counter stays 0
    # forever ("popular" sort + writer "total views" both permanently broken).
    await db.commit()
    return envelope_ok(data)


@reader_router.get("/{slug}/progress")
async def get_progress(
    slug: str,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """The reader's saved progress for a story (null if signed out / never read).

    The frontend Resume CTA, read-checkmarks and progress bar GET this; only PUT
    existed before, so every poll 405'd and those affordances never appeared.
    """
    if not user:
        return envelope_ok(None)
    progress = await rsvc.get_reader_progress(slug, user.id, db)
    return envelope_ok(progress)


@reader_router.get("/{slug}/chapters/{chapter_number}")
async def read_chapter(
    slug: str,
    chapter_number: int,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    reader_id = user.id if user else None
    data = await rsvc.get_chapter_for_reading(slug, chapter_number, reader_id, db)
    if reader_id:
        await db.commit()  # persist auto-created progress record
    return envelope_ok(data)


@reader_router.put("/{slug}/progress")
async def update_progress(
    slug: str,
    payload: ProgressUpdate,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        return envelope_ok(None)
    progress = await rsvc.update_progress(slug, payload, user.id, db)
    await db.commit()
    return envelope_ok(progress)


@reader_router.post("/{slug}/follow")
async def follow(
    slug: str,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        raise Unauthorized("sign in to follow stories")
    follow_obj = await rsvc.follow_publication(slug, user.id, db)
    await db.commit()
    return envelope_ok(follow_obj)


@reader_router.delete("/{slug}/follow")
async def unfollow(
    slug: str,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        return envelope_ok(None)
    await rsvc.unfollow_publication(slug, user.id, db)
    await db.commit()
    return envelope_ok({"unfollowed": True})
