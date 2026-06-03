"""
Writer profile endpoints.

GET  /v1/u/{user_id}          — public profile + published stories
GET  /v1/u/me                 — own profile (with private flag)
PUT  /v1/u/me                 — update display_name, bio, avatar, profile_public
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.core.deps import CurrentUser, DB, OptionalUser
from app.core.errors import envelope_ok, NotFound
from app.db.models import User, Story
from app.db.publishing_models import (
    Publication, PublicationChapter, StoryRating, ReaderProfile,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ProfileUpdate(BaseModel):
    display_name: Optional[str] = Field(None, max_length=120)
    bio:          Optional[str] = Field(None, max_length=500)
    avatar_url:   Optional[str] = None
    profile_public: Optional[bool] = None


class ProfileOut(BaseModel):
    user_id:       str
    display_name:  str
    bio:           Optional[str]
    avatar_url:    Optional[str]
    profile_public: bool
    story_count:   int
    total_reads:   int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_or_create_reader_profile(user_id: str, db: AsyncSession) -> ReaderProfile:
    rp = await db.get(ReaderProfile, user_id)
    if not rp:
        rp = ReaderProfile(user_id=user_id, is_age_verified=False)
        db.add(rp)
        await db.flush()
        await db.refresh(rp)
    return rp


async def _profile_payload(user: User, db: AsyncSession) -> dict:
    rp = await db.get(ReaderProfile, user.id)

    pubs = (await db.execute(
        select(Publication)
        .where(Publication.user_id == user.id)
        .where(Publication.status == "published")
        .order_by(Publication.published_at.desc())
    )).scalars().all()

    stories = []
    for pub in pubs:
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

        stories.append({
            "id":              pub.id,
            "slug":            pub.slug,
            "tagline":         pub.tagline,
            "genre":           pub.genre,
            "tags":            pub.tags,
            "cover_image_url": pub.cover_image_url,
            "release_type":    pub.release_type,
            "view_count":      pub.view_count or 0,
            "published_at":    pub.published_at.isoformat() if pub.published_at else None,
            "total_chapters":  chapter_count,
            "avg_rating":      round(float(agg.avg), 2) if agg.avg else None,
            "rating_count":    agg.cnt or 0,
        })

    # Get story titles from stories table
    for s in stories:
        pub = next((p for p in pubs if p.id == s["id"]), None)
        if pub:
            story = await db.get(Story, pub.story_id)
            s["story_title"] = story.title if story else "Untitled"

    total_reads = sum(s["view_count"] for s in stories)

    # Persisted privacy flag (reader_profiles.profile_public). Default public when
    # no ReaderProfile row exists yet.
    profile_public = rp.profile_public if rp else True

    return {
        "user_id":       user.id,
        # Never derive a public display name from the email local-part — that
        # leaks the address. Fall back to a neutral placeholder.
        "display_name":  user.display_name or "Anonymous",
        "bio":           rp.bio if rp else None,
        "avatar_url":    rp.avatar_url if rp else None,
        "profile_public": profile_public,
        "story_count":   len(stories),
        "total_reads":   total_reads,
        "stories":       stories,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/me")
async def my_profile(user: CurrentUser, db: DB):
    data = await _profile_payload(user, db)
    return envelope_ok(data)


@router.put("/me")
async def update_my_profile(payload: ProfileUpdate, user: CurrentUser, db: DB):
    rp = await _get_or_create_reader_profile(user.id, db)

    if payload.display_name is not None:
        user.display_name = payload.display_name
    if payload.bio is not None:
        rp.bio = payload.bio
    if payload.avatar_url is not None:
        rp.avatar_url = payload.avatar_url
    if payload.profile_public is not None:
        rp.profile_public = payload.profile_public

    await db.commit()
    data = await _profile_payload(user, db)
    return envelope_ok(data)


@router.get("/{user_id}")
async def public_profile(user_id: str, db: DB, viewer: OptionalUser = None):
    user = await db.get(User, user_id)
    if not user:
        raise NotFound("profile")

    rp = await db.get(ReaderProfile, user.id)
    is_public = rp.profile_public if rp else True
    # A private profile is only visible to its owner. Raise NotFound (not 403) to
    # stay consistent with the codebase's don't-leak-existence convention.
    if not is_public and (viewer is None or viewer.id != user.id):
        raise NotFound("profile")

    data = await _profile_payload(user, db)
    return envelope_ok(data)
