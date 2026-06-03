# apps/api/app/services/social_service.py

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound, Forbidden, BadRequest
from app.db.models import User
from app.db.publishing_models import (
    Publication, StoryRating, Review, PrivateNote,
    ReadingProgress, PublicationFollow,
)
from app.db.publishing_schemas import (
    RatingSubmit, ReviewSubmit, NoteSubmit, NoteReply,
    RatingAggregate, InboxStats, InboxResponse,
    ReviewOut, PrivateNoteOut,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _require_publication(pub_id: str, db: AsyncSession) -> Publication:
    pub = await db.get(Publication, pub_id)
    if not pub or pub.status not in ("published", "unlisted"):
        raise NotFound("publication")
    return pub


async def _require_writer_owns_pub(pub_id: str, user: User, db: AsyncSession) -> Publication:
    pub = await db.get(Publication, pub_id)
    if not pub:
        raise NotFound("publication")
    if pub.user_id != user.id:
        raise Forbidden("not your publication")
    return pub


async def _reader_chapter_count(reader_id: str, pub_id: str, db: AsyncSession) -> int:
    progress = (await db.execute(
        select(ReadingProgress)
        .where(ReadingProgress.reader_id == reader_id)
        .where(ReadingProgress.publication_id == pub_id)
    )).scalar_one_or_none()
    return progress.last_chapter_number if progress else 0


# ---------------------------------------------------------------------------
# Ratings
# ---------------------------------------------------------------------------

async def upsert_rating(
    pub_id: str, payload: RatingSubmit, reader_id: str, db: AsyncSession,
) -> StoryRating:
    await _require_publication(pub_id, db)

    chapters_read = await _reader_chapter_count(reader_id, pub_id, db)
    if chapters_read < 1:
        raise BadRequest("read at least the first chapter before rating")

    existing = (await db.execute(
        select(StoryRating)
        .where(StoryRating.reader_id == reader_id)
        .where(StoryRating.publication_id == pub_id)
    )).scalar_one_or_none()

    now = datetime.utcnow()
    if existing:
        existing.overall          = payload.overall
        existing.score_story      = payload.score_story
        existing.score_craft      = payload.score_craft
        existing.score_characters = payload.score_characters
        existing.score_pacing     = payload.score_pacing
        existing.score_world      = payload.score_world
        existing.updated_at       = now
        await db.flush()
        await db.refresh(existing)
        return existing

    rating = StoryRating(
        reader_id=reader_id,
        publication_id=pub_id,
        **payload.model_dump(),
    )
    db.add(rating)
    await db.flush()
    await db.refresh(rating)
    return rating


async def delete_rating(pub_id: str, reader_id: str, db: AsyncSession) -> None:
    rating = (await db.execute(
        select(StoryRating)
        .where(StoryRating.reader_id == reader_id)
        .where(StoryRating.publication_id == pub_id)
    )).scalar_one_or_none()
    if rating:
        await db.delete(rating)
        await db.flush()


async def get_rating_aggregate(pub_id: str, db: AsyncSession) -> RatingAggregate:
    await _require_publication(pub_id, db)  # don't expose ratings of unpublished/foreign pubs
    agg = (await db.execute(
        select(
            func.avg(StoryRating.overall).label("avg_overall"),
            func.count(StoryRating.id).label("count"),
            func.avg(StoryRating.score_story).label("avg_story"),
            func.avg(StoryRating.score_craft).label("avg_craft"),
            func.avg(StoryRating.score_characters).label("avg_characters"),
            func.avg(StoryRating.score_pacing).label("avg_pacing"),
            func.avg(StoryRating.score_world).label("avg_world"),
        )
        .where(StoryRating.publication_id == pub_id)
    )).one()

    dist_rows = (await db.execute(
        select(StoryRating.overall, func.count(StoryRating.id))
        .where(StoryRating.publication_id == pub_id)
        .group_by(StoryRating.overall)
    )).all()
    distribution = {i: 0 for i in range(1, 6)}
    for star, cnt in dist_rows:
        distribution[star] = cnt

    def _r(v) -> Optional[float]:
        return round(float(v), 2) if v is not None else None

    return RatingAggregate(
        avg_overall=_r(agg.avg_overall) or 0.0,
        count=agg.count or 0,
        avg_story=_r(agg.avg_story),
        avg_craft=_r(agg.avg_craft),
        avg_characters=_r(agg.avg_characters),
        avg_pacing=_r(agg.avg_pacing),
        avg_world=_r(agg.avg_world),
        distribution=distribution,
    )


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------

async def submit_review(
    pub_id: str, payload: ReviewSubmit, reader_id: str, db: AsyncSession,
) -> Review:
    await _require_publication(pub_id, db)

    progress = (await db.execute(
        select(ReadingProgress)
        .where(ReadingProgress.reader_id == reader_id)
        .where(ReadingProgress.publication_id == pub_id)
    )).scalar_one_or_none()

    has_read = progress is not None and progress.last_chapter_number >= 1
    if not has_read:
        raise BadRequest("open at least one chapter before leaving a review")

    existing = (await db.execute(
        select(Review)
        .where(Review.reader_id == reader_id)
        .where(Review.publication_id == pub_id)
    )).scalar_one_or_none()
    if existing:
        raise BadRequest("you have already submitted a review for this story")

    review = Review(
        reader_id=reader_id,
        publication_id=pub_id,
        body=payload.body,
        status="pending",
    )
    db.add(review)
    await db.flush()
    await db.refresh(review)
    return review


async def get_public_reviews(pub_id: str, db: AsyncSession) -> list[dict]:
    await _require_publication(pub_id, db)  # don't expose reviews of unpublished/foreign pubs
    rows = (await db.execute(
        select(Review, User.display_name)
        .join(User, User.id == Review.reader_id)
        .where(Review.publication_id == pub_id)
        .where(Review.status == "approved")
        .order_by(Review.approved_at.desc())
    )).all()
    return [
        {**ReviewOut.model_validate(r).model_dump(), "reader_display_name": name}
        for r, name in rows
    ]


async def get_pending_reviews(pub_id: str, writer: User, db: AsyncSession) -> list[Review]:
    await _require_writer_owns_pub(pub_id, writer, db)
    return (await db.execute(
        select(Review)
        .where(Review.publication_id == pub_id)
        .where(Review.status == "pending")
        .order_by(Review.created_at.asc())
    )).scalars().all()


async def approve_review(review_id: str, writer: User, db: AsyncSession) -> Review:
    review = await db.get(Review, review_id)
    if not review:
        raise NotFound("review")
    await _require_writer_owns_pub(review.publication_id, writer, db)
    review.status = "approved"
    review.approved_at = datetime.utcnow()
    await db.flush()
    await db.refresh(review)
    return review


async def decline_review(review_id: str, writer: User, db: AsyncSession) -> Review:
    review = await db.get(Review, review_id)
    if not review:
        raise NotFound("review")
    await _require_writer_owns_pub(review.publication_id, writer, db)
    review.status = "declined"
    await db.flush()
    await db.refresh(review)
    return review


async def flag_review(
    review_id: str, reason: Optional[str], writer: User, db: AsyncSession
) -> Review:
    review = await db.get(Review, review_id)
    if not review:
        raise NotFound("review")
    await _require_writer_owns_pub(review.publication_id, writer, db)
    review.status = "flagged"
    review.flagged_reason = reason
    await db.flush()
    await db.refresh(review)
    return review


# ---------------------------------------------------------------------------
# Private Notes
# ---------------------------------------------------------------------------

async def send_note(
    pub_id: str, payload: NoteSubmit, reader_id: str, db: AsyncSession,
) -> PrivateNote:
    await _require_publication(pub_id, db)

    # Same anti-spam gate as ratings/reviews: a note is passage feedback, so the
    # sender must have actually opened a chapter (progress is only recordable on a
    # real published chapter now, so this can't be faked).
    if await _reader_chapter_count(reader_id, pub_id, db) < 1:
        raise BadRequest("open at least one chapter before sending a note")

    note = PrivateNote(
        reader_id=reader_id,
        publication_id=pub_id,
        chapter_number=payload.chapter_number,
        passage_reference=payload.passage_reference,
        body=payload.body,
    )
    db.add(note)
    await db.flush()
    await db.refresh(note)
    return note


async def get_notes_for_publication(pub_id: str, writer: User, db: AsyncSession) -> list[dict]:
    await _require_writer_owns_pub(pub_id, writer, db)
    rows = (await db.execute(
        select(PrivateNote, User.display_name)
        .join(User, User.id == PrivateNote.reader_id)
        .where(PrivateNote.publication_id == pub_id)
        .order_by(PrivateNote.created_at.desc())
    )).all()
    return [
        {**PrivateNoteOut.model_validate(n).model_dump(), "reader_display_name": name}
        for n, name in rows
    ]


async def reply_to_note(
    note_id: str, payload: NoteReply, writer: User, db: AsyncSession
) -> PrivateNote:
    note = await db.get(PrivateNote, note_id)
    if not note:
        raise NotFound("note")
    await _require_writer_owns_pub(note.publication_id, writer, db)
    note.writer_reply = payload.reply
    note.replied_at = datetime.utcnow()
    await db.flush()
    await db.refresh(note)
    return note


async def mark_note_read(note_id: str, writer: User, db: AsyncSession) -> None:
    note = await db.get(PrivateNote, note_id)
    if not note:
        raise NotFound("note")
    await _require_writer_owns_pub(note.publication_id, writer, db)
    note.is_read_by_writer = True
    await db.flush()


# ---------------------------------------------------------------------------
# Writer Inbox
# ---------------------------------------------------------------------------

async def get_writer_inbox(writer: User, db: AsyncSession) -> InboxResponse:
    from app.db.models import Story
    pubs = (await db.execute(
        select(Publication, Story.title)
        .join(Story, Story.id == Publication.story_id)
        .where(Publication.user_id == writer.id)
    )).all()

    if not pubs:
        return InboxResponse(
            stats=InboxStats(
                total_views=0, total_ratings=0, avg_rating=None,
                total_reviews=0, pending_reviews=0,
                total_notes=0, unread_notes=0, followers=0,
            ),
            recent=[],
            pending_reviews=[],
            unread_notes=[],
        )

    pub_ids = [p.id for p, _ in pubs]

    view_total = sum(p.view_count for p, _ in pubs)

    rating_agg = (await db.execute(
        select(
            func.count(StoryRating.id).label("cnt"),
            func.avg(StoryRating.overall).label("avg"),
        )
        .where(StoryRating.publication_id.in_(pub_ids))
    )).one()

    review_total = (await db.execute(
        select(func.count(Review.id))
        .where(Review.publication_id.in_(pub_ids))
    )).scalar_one()

    review_pending = (await db.execute(
        select(func.count(Review.id))
        .where(Review.publication_id.in_(pub_ids))
        .where(Review.status == "pending")
    )).scalar_one()

    note_total = (await db.execute(
        select(func.count(PrivateNote.id))
        .where(PrivateNote.publication_id.in_(pub_ids))
    )).scalar_one()

    note_unread = (await db.execute(
        select(func.count(PrivateNote.id))
        .where(PrivateNote.publication_id.in_(pub_ids))
        .where(PrivateNote.is_read_by_writer == False)  # noqa: E712
    )).scalar_one()

    followers = (await db.execute(
        select(func.count(PublicationFollow.reader_id))
        .where(PublicationFollow.publication_id.in_(pub_ids))
    )).scalar_one()

    stats = InboxStats(
        total_views=view_total,
        total_ratings=rating_agg.cnt or 0,
        avg_rating=round(float(rating_agg.avg), 2) if rating_agg.avg else None,
        total_reviews=review_total or 0,
        pending_reviews=review_pending or 0,
        total_notes=note_total or 0,
        unread_notes=note_unread or 0,
        followers=followers or 0,
    )

    pending_reviews_rows = (await db.execute(
        select(Review, User.display_name)
        .join(User, User.id == Review.reader_id)
        .where(Review.publication_id.in_(pub_ids))
        .where(Review.status == "pending")
        .order_by(Review.created_at.asc())
        .limit(20)
    )).all()
    pending_reviews = [
        {**ReviewOut.model_validate(r).model_dump(), "reader_display_name": name}
        for r, name in pending_reviews_rows
    ]

    unread_notes_rows = (await db.execute(
        select(PrivateNote, User.display_name)
        .join(User, User.id == PrivateNote.reader_id)
        .where(PrivateNote.publication_id.in_(pub_ids))
        .where(PrivateNote.is_read_by_writer == False)  # noqa: E712
        .order_by(PrivateNote.created_at.desc())
        .limit(20)
    )).all()
    unread_notes = [
        {**PrivateNoteOut.model_validate(n).model_dump(), "reader_display_name": name}
        for n, name in unread_notes_rows
    ]

    return InboxResponse(
        stats=stats,
        recent=[],
        pending_reviews=pending_reviews,
        unread_notes=unread_notes,
    )


async def get_unread_count(writer: User, db: AsyncSession) -> int:
    pub_ids = (await db.execute(
        select(Publication.id).where(Publication.user_id == writer.id)
    )).scalars().all()
    if not pub_ids:
        return 0
    pending = (await db.execute(
        select(func.count(Review.id))
        .where(Review.publication_id.in_(pub_ids))
        .where(Review.status == "pending")
    )).scalar_one()
    unread = (await db.execute(
        select(func.count(PrivateNote.id))
        .where(PrivateNote.publication_id.in_(pub_ids))
        .where(PrivateNote.is_read_by_writer == False)  # noqa: E712
    )).scalar_one()
    return (pending or 0) + (unread or 0)
