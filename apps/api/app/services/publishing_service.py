# apps/api/app/services/publishing_service.py

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Optional

from slugify import slugify
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound, Forbidden, BadRequest
from app.db.models import Story, Chapter, User
from app.db.publishing_models import Publication, PublicationChapter
from app.db.publishing_schemas import (
    PublicationCreate, PublicationUpdate, PushChaptersRequest,
)

_utcnow = datetime.utcnow  # naive — matches DateTime (no tz) columns in publishing_models


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_owned_publication(
    pub_id: str, user: User, db: AsyncSession
) -> Publication:
    row = await db.get(Publication, pub_id)
    if not row:
        raise NotFound("publication")
    if row.user_id != user.id:
        raise Forbidden("not your publication")
    return row


async def _unique_slug(base: str, db: AsyncSession) -> str:
    candidate = slugify(base)[:180]
    existing = (await db.execute(
        select(Publication.slug).where(Publication.slug == candidate)
    )).scalar_one_or_none()
    if not existing:
        return candidate
    suffix = uuid.uuid4().hex[:6]
    return f"{candidate}-{suffix}"


def _count_words(text: str) -> int:
    return len(re.findall(r"\w+", text))


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

async def create_publication(
    payload: PublicationCreate, user: User, db: AsyncSession
) -> Publication:
    story = await db.get(Story, payload.story_id)
    if not story or story.user_id != user.id:
        raise NotFound("story")

    existing = (await db.execute(
        select(Publication).where(Publication.story_id == payload.story_id)
    )).scalar_one_or_none()
    if existing:
        raise BadRequest("story already has a publication")

    slug = await _unique_slug(story.title or "untitled", db)

    pub = Publication(
        story_id=payload.story_id,
        user_id=user.id,
        slug=slug,
        release_type=payload.release_type,
        tagline=payload.tagline,
        genre=payload.genre or story.genre,
        tags=payload.tags,
        content_warnings=payload.content_warnings,
        cover_image_url=payload.cover_image_url,
        total_planned_chapters=payload.total_planned_chapters,
        status="draft",
    )
    db.add(pub)
    await db.flush()
    await db.refresh(pub)
    return pub


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

async def update_publication(
    pub_id: str, payload: PublicationUpdate, user: User, db: AsyncSession
) -> Publication:
    pub = await _get_owned_publication(pub_id, user, db)

    if payload.tagline is not None:
        pub.tagline = payload.tagline
    if payload.genre is not None:
        pub.genre = payload.genre
    if payload.tags is not None:
        pub.tags = payload.tags
    if payload.content_warnings is not None:
        pub.content_warnings = payload.content_warnings
    if payload.cover_image_url is not None:
        pub.cover_image_url = payload.cover_image_url
    if payload.release_type is not None:
        pub.release_type = payload.release_type
    if payload.total_planned_chapters is not None:
        pub.total_planned_chapters = payload.total_planned_chapters

    pub.updated_at = _utcnow()
    await db.flush()
    await db.refresh(pub)
    return pub


# ---------------------------------------------------------------------------
# Push chapters
# ---------------------------------------------------------------------------

async def push_chapters(
    pub_id: str, req: PushChaptersRequest, user: User, db: AsyncSession
) -> list[PublicationChapter]:
    pub = await _get_owned_publication(pub_id, user, db)

    chapters = (await db.execute(
        select(Chapter)
        .where(Chapter.story_id == pub.story_id)
        .where(Chapter.number.in_(req.chapter_numbers))
    )).scalars().all()

    found_numbers = {c.number for c in chapters}
    missing = set(req.chapter_numbers) - found_numbers
    if missing:
        raise BadRequest(f"chapters not found: {sorted(missing)}")

    pushed: list[PublicationChapter] = []
    new_chapters: list[tuple[int, str]] = []  # (number, title) for version==1 → notify followers

    for chapter in sorted(chapters, key=lambda c: c.number):
        await db.execute(
            update(PublicationChapter)
            .where(PublicationChapter.publication_id == pub_id)
            .where(PublicationChapter.chapter_number == chapter.number)
            .values(is_latest=False)
        )

        latest = (await db.execute(
            select(PublicationChapter.version)
            .where(PublicationChapter.publication_id == pub_id)
            .where(PublicationChapter.chapter_number == chapter.number)
            .order_by(PublicationChapter.version.desc())
            .limit(1)
        )).scalar_one_or_none()
        new_version = (latest or 0) + 1

        snap = PublicationChapter(
            publication_id=pub_id,
            chapter_number=chapter.number,
            version=new_version,
            title=chapter.title or f"Chapter {chapter.number}",
            content=chapter.content or "",
            word_count=_count_words(chapter.content or ""),
            is_latest=True,
        )
        db.add(snap)
        pushed.append(snap)
        if new_version == 1:  # first time this chapter number goes public → a "new chapter"
            new_chapters.append((chapter.number, chapter.title or ""))

    pub.last_chapter_pushed_at = _utcnow()
    pub.updated_at = _utcnow()
    await db.flush()

    # Fan out in-app notifications to followers for genuinely-new chapters. Only
    # meaningful once the pub is public (drafts have no followers); best-effort.
    if new_chapters and pub.status in ("published", "unlisted"):
        from app.services import notification_service
        story = await db.get(Story, pub.story_id)
        await notification_service.notify_new_chapters(
            db, pub, (story.title if story else "a story you follow"), new_chapters
        )

    return pushed


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------

async def go_live(pub_id: str, user: User, db: AsyncSession) -> Publication:
    pub = await _get_owned_publication(pub_id, user, db)

    chapter_count = (await db.execute(
        select(PublicationChapter)
        .where(PublicationChapter.publication_id == pub_id)
        .where(PublicationChapter.is_latest == True)  # noqa: E712
    )).scalars().first()
    if not chapter_count:
        raise BadRequest("cannot publish: no chapters have been pushed yet")

    pub.status = "published"
    if not pub.published_at:
        pub.published_at = _utcnow()
    pub.updated_at = _utcnow()
    await db.flush()
    await db.refresh(pub)
    return pub


async def unpublish(pub_id: str, user: User, db: AsyncSession) -> Publication:
    pub = await _get_owned_publication(pub_id, user, db)
    pub.status = "unlisted"
    pub.updated_at = _utcnow()
    await db.flush()
    await db.refresh(pub)
    return pub


async def archive(pub_id: str, user: User, db: AsyncSession) -> Publication:
    pub = await _get_owned_publication(pub_id, user, db)
    pub.status = "archived"
    pub.updated_at = _utcnow()
    await db.flush()
    await db.refresh(pub)
    return pub


async def delete_publication(pub_id: str, user: User, db: AsyncSession) -> None:
    pub = await _get_owned_publication(pub_id, user, db)
    if pub.status == "published":
        raise BadRequest("cannot delete a live publication — unpublish first")
    await db.delete(pub)
    await db.flush()


# ---------------------------------------------------------------------------
# Read (writer dashboard)
# ---------------------------------------------------------------------------

async def list_pushed_chapters(
    pub_id: str, user: User, db: AsyncSession
) -> list[PublicationChapter]:
    """Return the latest snapshot of every chapter pushed to this publication."""
    await _get_owned_publication(pub_id, user, db)  # ownership check
    return (await db.execute(
        select(PublicationChapter)
        .where(PublicationChapter.publication_id == pub_id)
        .where(PublicationChapter.is_latest == True)  # noqa: E712
        .order_by(PublicationChapter.chapter_number)
    )).scalars().all()


async def get_writer_publication(
    story_id: str, user: User, db: AsyncSession
) -> Optional[Publication]:
    return (await db.execute(
        select(Publication)
        .where(Publication.story_id == story_id)
        .where(Publication.user_id == user.id)
    )).scalar_one_or_none()


async def list_writer_publications(user: User, db: AsyncSession) -> list[Publication]:
    return (await db.execute(
        select(Publication)
        .where(Publication.user_id == user.id)
        .order_by(Publication.updated_at.desc())
    )).scalars().all()
