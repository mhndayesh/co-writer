from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.errors import envelope_ok
from app.db.models import User
from app.db.publishing_schemas import (
    RatingSubmit, ReviewSubmit, ReviewAction, NoteSubmit, NoteReply,
)
from app.services import social_service as ssvc

social_router = APIRouter()

# ── Ratings ──────────────────────────────────────────────────────────────────

@social_router.post("/{pub_id}/rate")
async def rate(
    pub_id: str,
    payload: RatingSubmit,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rating = await ssvc.upsert_rating(pub_id, payload, user.id, db)
    await db.commit()
    return envelope_ok(rating)


@social_router.delete("/{pub_id}/rate")
async def delete_rate(
    pub_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await ssvc.delete_rating(pub_id, user.id, db)
    await db.commit()
    return envelope_ok({"deleted": True})


@social_router.get("/{pub_id}/ratings")
async def rating_stats(
    pub_id: str,
    db: AsyncSession = Depends(get_db),
):
    agg = await ssvc.get_rating_aggregate(pub_id, db)
    return envelope_ok(agg)


# ── Reviews ───────────────────────────────────────────────────────────────────

@social_router.post("/{pub_id}/review")
async def submit_review(
    pub_id: str,
    payload: ReviewSubmit,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    review = await ssvc.submit_review(pub_id, payload, user.id, db)
    await db.commit()
    return envelope_ok(review)


@social_router.get("/{pub_id}/reviews")
async def get_reviews(
    pub_id: str,
    db: AsyncSession = Depends(get_db),
):
    reviews = await ssvc.get_public_reviews(pub_id, db)
    return envelope_ok(reviews)


@social_router.get("/{pub_id}/reviews/pending")
async def get_pending(
    pub_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    reviews = await ssvc.get_pending_reviews(pub_id, user, db)
    return envelope_ok(reviews)


@social_router.post("/reviews/{review_id}/approve")
async def approve(
    review_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = await ssvc.approve_review(review_id, user, db)
    await db.commit()
    return envelope_ok(r)


@social_router.post("/reviews/{review_id}/decline")
async def decline(
    review_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = await ssvc.decline_review(review_id, user, db)
    await db.commit()
    return envelope_ok(r)


@social_router.post("/reviews/{review_id}/flag")
async def flag(
    review_id: str,
    payload: ReviewAction,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = await ssvc.flag_review(review_id, payload.flagged_reason, user, db)
    await db.commit()
    return envelope_ok(r)


# ── Private Notes ─────────────────────────────────────────────────────────────

@social_router.post("/{pub_id}/note")
async def send_note(
    pub_id: str,
    payload: NoteSubmit,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    note = await ssvc.send_note(pub_id, payload, user.id, db)
    await db.commit()
    return envelope_ok(note)


@social_router.get("/{pub_id}/notes")
async def get_notes(
    pub_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    notes = await ssvc.get_notes_for_publication(pub_id, user, db)
    return envelope_ok(notes)


@social_router.post("/notes/{note_id}/reply")
async def reply_note(
    note_id: str,
    payload: NoteReply,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    note = await ssvc.reply_to_note(note_id, payload, user, db)
    await db.commit()
    return envelope_ok(note)


@social_router.put("/notes/{note_id}/read")
async def mark_read(
    note_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await ssvc.mark_note_read(note_id, user, db)
    await db.commit()
    return envelope_ok({"read": True})
