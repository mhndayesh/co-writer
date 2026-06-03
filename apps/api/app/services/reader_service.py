# apps/api/app/services/reader_service.py

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import func, select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound
from app.db.models import Story, User
from app.db.publishing_models import (
    Publication, PublicationChapter, ReadingProgress,
    PublicationFollow, StoryRating,
)
from app.db.publishing_schemas import (
    ProgressUpdate, PublicationSummary, DiscoveryFeedResponse,
)


# ---------------------------------------------------------------------------
# Discovery feed
# ---------------------------------------------------------------------------

VALID_SORTS = {"recent", "popular", "rating"}
VALID_GENRES = {
    "fantasy", "sci-fi", "thriller", "romance", "literary",
    "mystery", "horror", "historical", "adventure", "young-adult", "other",
}


async def get_discovery_feed(
    db: AsyncSession,
    page: int = 1,
    per_page: int = 20,
    genre: Optional[str] = None,
    sort: str = "recent",
    search: Optional[str] = None,
) -> DiscoveryFeedResponse:
    per_page = min(per_page, 50)
    offset = (page - 1) * per_page

    q = (
        select(
            Publication,
            Story.title.label("story_title"),
            User.display_name.label("author_name"),
        )
        .join(Story, Story.id == Publication.story_id)
        .join(User,  User.id == Publication.user_id)
        .where(Publication.status == "published")
    )

    if genre and genre in VALID_GENRES:
        q = q.where(Publication.genre == genre)

    if search:
        # Escape LIKE wildcards in user input so a query of "%" / "_" can't match
        # everything (a mild DoS / scan amplifier); already parameterized, so no
        # injection — this is purely about wildcard semantics.
        safe = search.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{safe}%"
        q = q.where(
            (func.lower(Story.title).like(pattern, escape="\\")) |
            (func.lower(Publication.tagline).like(pattern, escape="\\")) |
            (func.lower(User.display_name).like(pattern, escape="\\"))
        )

    if sort == "popular":
        q = q.order_by(Publication.view_count.desc(), Publication.published_at.desc())
    else:
        q = q.order_by(Publication.published_at.desc())

    total_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(total_q)).scalar_one()

    rows = (await db.execute(q.offset(offset).limit(per_page))).all()

    items = []
    for pub, story_title, author_name in rows:
        chapter_count = (await db.execute(
            select(func.count()).where(
                and_(
                    PublicationChapter.publication_id == pub.id,
                    PublicationChapter.is_latest == True,  # noqa: E712
                )
            )
        )).scalar_one()

        agg = (await db.execute(
            select(
                func.avg(StoryRating.overall).label("avg"),
                func.count(StoryRating.id).label("cnt"),
            )
            .where(StoryRating.publication_id == pub.id)
        )).one()

        items.append(PublicationSummary(
            id=pub.id,
            slug=pub.slug,
            author_id=pub.user_id,
            story_title=story_title,
            author_name=author_name or "",
            tagline=pub.tagline,
            genre=pub.genre,
            tags=pub.tags,
            cover_image_url=pub.cover_image_url,
            content_warnings=pub.content_warnings,
            release_type=pub.release_type,
            status=pub.status,
            view_count=pub.view_count,
            published_at=pub.published_at,
            total_chapters=chapter_count,
            avg_rating=round(float(agg.avg), 2) if agg.avg else None,
            rating_count=agg.cnt or 0,
        ))

    if sort == "rating":
        items.sort(key=lambda x: (x.avg_rating or 0), reverse=True)

    return DiscoveryFeedResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        has_more=(offset + per_page) < total,
    )


# ---------------------------------------------------------------------------
# Story landing page
# ---------------------------------------------------------------------------

async def get_story_landing(slug: str, db: AsyncSession) -> dict:
    row = (await db.execute(
        select(Publication, Story, User)
        .join(Story, Story.id == Publication.story_id)
        .join(User,  User.id == Publication.user_id)
        .where(Publication.slug == slug)
        .where(Publication.status.in_(["published", "unlisted"]))
    )).one_or_none()

    if not row:
        raise NotFound("publication")

    pub, story, author = row

    chapters = (await db.execute(
        select(PublicationChapter)
        .where(PublicationChapter.publication_id == pub.id)
        .where(PublicationChapter.is_latest == True)  # noqa: E712
        .order_by(PublicationChapter.chapter_number)
    )).scalars().all()

    agg = (await db.execute(
        select(
            func.avg(StoryRating.overall).label("avg"),
            func.count(StoryRating.id).label("cnt"),
        )
        .where(StoryRating.publication_id == pub.id)
    )).one()

    try:
        await db.execute(
            update(Publication)
            .where(Publication.id == pub.id)
            .values(view_count=Publication.view_count + 1)
        )
        await db.flush()
        pub.view_count = (pub.view_count or 0) + 1
    except Exception:
        pass

    return {
        "publication": pub,
        "story_title": story.title,
        "story_logline": None,
        "author_name": author.display_name or author.email.split("@")[0],
        "chapters": chapters,
        "avg_rating": round(float(agg.avg), 2) if agg.avg else None,
        "rating_count": agg.cnt or 0,
    }


# ---------------------------------------------------------------------------
# Get a single chapter for reading
# ---------------------------------------------------------------------------

async def get_chapter_for_reading(
    slug: str,
    chapter_number: int,
    reader_id: Optional[str],
    db: AsyncSession,
) -> dict:
    row = (await db.execute(
        select(Publication, Story.title, User.display_name, User.email)
        .join(Story, Story.id == Publication.story_id)
        .join(User,  User.id == Publication.user_id)
        .where(Publication.slug == slug)
        .where(Publication.status.in_(["published", "unlisted"]))
    )).one_or_none()

    if not row:
        raise NotFound("publication")

    pub, story_title, author_display, author_email = row

    chapter = (await db.execute(
        select(PublicationChapter)
        .where(PublicationChapter.publication_id == pub.id)
        .where(PublicationChapter.chapter_number == chapter_number)
        .where(PublicationChapter.is_latest == True)  # noqa: E712
    )).scalar_one_or_none()

    if not chapter:
        raise NotFound("chapter")

    total = (await db.execute(
        select(func.count())
        .where(
            and_(
                PublicationChapter.publication_id == pub.id,
                PublicationChapter.is_latest == True,  # noqa: E712
            )
        )
    )).scalar_one()

    progress = None
    if reader_id:
        progress = (await db.execute(
            select(ReadingProgress)
            .where(ReadingProgress.reader_id == reader_id)
            .where(ReadingProgress.publication_id == pub.id)
        )).scalar_one_or_none()

        # Auto-record that this reader has opened the story (enables reviews)
        if not progress:
            progress = ReadingProgress(
                reader_id=reader_id,
                publication_id=pub.id,
                last_chapter_number=chapter_number,
                completion_percentage=1.0,
            )
            db.add(progress)
            await db.flush()
        elif progress.last_chapter_number < chapter_number:
            progress.last_chapter_number = chapter_number

    return {
        "chapter": chapter,
        "total_chapters": total,
        "pub_slug": slug,
        "pub_id": pub.id,
        "progress": progress,
        # Carried so the reader UI can show the story title / author (e.g. the
        # "You finished …" card) without a second round-trip to the landing page
        # (which would also wrongly bump view_count on every chapter open).
        "story_title": story_title,
        "author_name": author_display or (author_email.split("@")[0] if author_email else ""),
    }


# ---------------------------------------------------------------------------
# Read reading progress (GET)
# ---------------------------------------------------------------------------

async def get_reader_progress(
    slug: str,
    reader_id: str,
    db: AsyncSession,
) -> Optional[ReadingProgress]:
    """This reader's saved progress for a story, or None if they've never read it.

    Read-only (no auto-create): a landing-page poll shouldn't mint a progress row
    and thereby unlock the rating gate for someone who only glanced at the cover.
    """
    pub = (await db.execute(
        select(Publication)
        .where(Publication.slug == slug)
        .where(Publication.status.in_(["published", "unlisted"]))
    )).scalar_one_or_none()
    if not pub:
        raise NotFound("publication")

    return (await db.execute(
        select(ReadingProgress)
        .where(ReadingProgress.reader_id == reader_id)
        .where(ReadingProgress.publication_id == pub.id)
    )).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Update reading progress
# ---------------------------------------------------------------------------

async def update_progress(
    slug: str,
    payload: ProgressUpdate,
    reader_id: str,
    db: AsyncSession,
) -> ReadingProgress:
    pub = (await db.execute(
        select(Publication)
        .where(Publication.slug == slug)
        .where(Publication.status.in_(["published", "unlisted"]))
    )).scalar_one_or_none()
    if not pub:
        raise NotFound("publication")

    # The rating/review "must have read a chapter" gate keys off
    # last_chapter_number, so progress may only point at a chapter that actually
    # exists in THIS publication — otherwise anyone could POST arbitrary progress
    # to unlock rating/reviewing (and flooding notes on) a story they never read.
    chapter_exists = (await db.execute(
        select(PublicationChapter.id)
        .where(PublicationChapter.publication_id == pub.id)
        .where(PublicationChapter.chapter_number == payload.chapter_number)
        .where(PublicationChapter.is_latest == True)  # noqa: E712
    )).scalar_one_or_none()
    if chapter_exists is None:
        raise NotFound("chapter")

    progress = (await db.execute(
        select(ReadingProgress)
        .where(ReadingProgress.reader_id == reader_id)
        .where(ReadingProgress.publication_id == pub.id)
    )).scalar_one_or_none()

    now = datetime.utcnow()
    if not progress:
        progress = ReadingProgress(
            reader_id=reader_id,
            publication_id=pub.id,
            last_chapter_number=payload.chapter_number,
            completion_percentage=payload.completion_percentage,
        )
        db.add(progress)
    else:
        if payload.chapter_number >= progress.last_chapter_number:
            progress.last_chapter_number = payload.chapter_number
        progress.completion_percentage = max(
            progress.completion_percentage, payload.completion_percentage
        )
        progress.last_read_at = now
        if payload.completion_percentage >= 99.0 and not progress.completed_at:
            progress.completed_at = now

    await db.flush()
    await db.refresh(progress)
    return progress


# ---------------------------------------------------------------------------
# Follow / unfollow
# ---------------------------------------------------------------------------

async def follow_publication(slug: str, reader_id: str, db: AsyncSession) -> PublicationFollow:
    pub = (await db.execute(
        select(Publication)
        .where(Publication.slug == slug)
        .where(Publication.status.in_(["published", "unlisted"]))
    )).scalar_one_or_none()
    if not pub:
        raise NotFound("publication")

    existing = await db.get(PublicationFollow, (reader_id, pub.id))
    if existing:
        return existing

    follow = PublicationFollow(reader_id=reader_id, publication_id=pub.id)
    db.add(follow)

    progress = (await db.execute(
        select(ReadingProgress)
        .where(ReadingProgress.reader_id == reader_id)
        .where(ReadingProgress.publication_id == pub.id)
    )).scalar_one_or_none()
    if progress:
        progress.is_following = True

    await db.flush()
    await db.refresh(follow)
    return follow


async def unfollow_publication(slug: str, reader_id: str, db: AsyncSession) -> None:
    pub = (await db.execute(
        select(Publication).where(Publication.slug == slug)
    )).scalar_one_or_none()
    if not pub:
        raise NotFound("publication")

    follow = await db.get(PublicationFollow, (reader_id, pub.id))
    if follow:
        await db.delete(follow)

    progress = (await db.execute(
        select(ReadingProgress)
        .where(ReadingProgress.reader_id == reader_id)
        .where(ReadingProgress.publication_id == pub.id)
    )).scalar_one_or_none()
    if progress:
        progress.is_following = False

    await db.flush()


# ---------------------------------------------------------------------------
# Reader library
# ---------------------------------------------------------------------------

async def get_reader_library(reader_id: str, db: AsyncSession) -> dict:
    # in_progress / completed come from reading progress…
    rows = (await db.execute(
        select(ReadingProgress, Publication, Story)
        .join(Publication, Publication.id == ReadingProgress.publication_id)
        .join(Story, Story.id == Publication.story_id)
        .where(ReadingProgress.reader_id == reader_id)
        .order_by(ReadingProgress.last_read_at.desc())
    )).all()

    in_progress, completed = [], []
    for progress, pub, story in rows:
        item = {
            "slug": pub.slug,
            "title": story.title,
            "cover_image_url": pub.cover_image_url,
            "last_chapter": progress.last_chapter_number,
            "completion": progress.completion_percentage,
            "last_read_at": progress.last_read_at,
            "is_following": progress.is_following,
        }
        (completed if progress.completed_at else in_progress).append(item)

    # …but "following" (saved) is canonical from PublicationFollow, so a story the
    # reader saved WITHOUT opening still shows up (the old is_following-on-progress
    # path silently dropped those).
    follow_rows = (await db.execute(
        select(PublicationFollow, Publication, Story)
        .join(Publication, Publication.id == PublicationFollow.publication_id)
        .join(Story, Story.id == Publication.story_id)
        .where(PublicationFollow.reader_id == reader_id)
        .order_by(PublicationFollow.followed_at.desc())
    )).all()

    progress_by_pub = {p.publication_id: p for p, _, _ in rows}
    following = []
    for follow, pub, story in follow_rows:
        prog = progress_by_pub.get(pub.id)
        following.append({
            "slug": pub.slug,
            "title": story.title,
            "cover_image_url": pub.cover_image_url,
            "last_chapter": prog.last_chapter_number if prog else 0,
            "completion": prog.completion_percentage if prog else 0.0,
            "followed_at": follow.followed_at,
            "notification_pref": follow.notification_pref,
            "is_following": True,
        })

    return {"in_progress": in_progress, "completed": completed, "following": following}
