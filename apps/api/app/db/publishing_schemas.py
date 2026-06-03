# apps/api/app/db/publishing_schemas.py

from __future__ import annotations
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


def _validate_image_url(v: Optional[str]) -> Optional[str]:
    """Allow http(s) image URLs OR same-origin uploaded paths (/v1/media/…). Blocks
    javascript:/data:/file:/protocol-relative // that would otherwise be rendered
    into <img src> on public reader pages."""
    if v is None:
        return v
    s = v.strip()
    if not s:
        return None
    is_same_origin = s.startswith("/") and not s.startswith("//")
    if not (is_same_origin or s.lower().startswith(("http://", "https://"))):
        raise ValueError("cover_image_url must be an http(s) URL or an uploaded path")
    if len(s) > 2048:
        raise ValueError("cover_image_url is too long")
    return s


# ---------------------------------------------------------------------------
# Publication
# ---------------------------------------------------------------------------

class PublicationCreate(BaseModel):
    story_id: str
    release_type: str = "complete"
    tagline: Optional[str] = Field(None, max_length=300)
    genre: Optional[str] = Field(None, max_length=60)
    tags: List[str] = []
    content_warnings: List[str] = []
    cover_image_url: Optional[str] = None
    total_planned_chapters: Optional[int] = None

    _v_cover = field_validator("cover_image_url")(_validate_image_url)


class PublicationUpdate(BaseModel):
    tagline: Optional[str] = Field(None, max_length=300)
    genre: Optional[str] = Field(None, max_length=60)
    tags: Optional[List[str]] = None
    content_warnings: Optional[List[str]] = None
    cover_image_url: Optional[str] = None
    release_type: Optional[str] = None
    total_planned_chapters: Optional[int] = None

    _v_cover = field_validator("cover_image_url")(_validate_image_url)


class PublicationOut(BaseModel):
    id: UUID
    story_id: UUID
    slug: str
    status: str
    release_type: str
    cover_image_url: Optional[str]
    tagline: Optional[str]
    content_warnings: List[str]
    genre: Optional[str]
    tags: List[str]
    published_at: Optional[datetime]
    last_chapter_pushed_at: Optional[datetime]
    total_planned_chapters: Optional[int]
    view_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PublicationSummary(BaseModel):
    """Lightweight version for feeds and cards."""
    id: str
    slug: str
    author_id: str          # user_id — used for profile links
    story_title: str
    author_name: str
    tagline: Optional[str]
    genre: Optional[str]
    tags: List[str]
    cover_image_url: Optional[str]
    content_warnings: List[str]
    release_type: str
    status: str
    view_count: int
    published_at: Optional[datetime]
    total_chapters: int
    avg_rating: Optional[float]
    rating_count: int

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# PublicationChapter
# ---------------------------------------------------------------------------

class PushChaptersRequest(BaseModel):
    chapter_numbers: List[int] = Field(..., min_length=1)
    """Chapter numbers (from the studio chapters table) to push."""


class PublicationChapterOut(BaseModel):
    id: UUID
    publication_id: UUID
    chapter_number: int
    version: int
    title: str
    word_count: int
    pushed_at: datetime
    is_latest: bool

    model_config = {"from_attributes": True}


class PublicationChapterContent(PublicationChapterOut):
    """Full chapter with content — only served on the reading route."""
    content: str


# ---------------------------------------------------------------------------
# ReaderProfile
# ---------------------------------------------------------------------------

class ReaderProfileUpdate(BaseModel):
    display_name: Optional[str] = Field(None, max_length=80)
    bio: Optional[str] = Field(None, max_length=500)
    avatar_url: Optional[str] = None


class ReaderProfileOut(BaseModel):
    user_id: UUID
    display_name: Optional[str]
    bio: Optional[str]
    avatar_url: Optional[str]
    is_age_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# ReadingProgress
# ---------------------------------------------------------------------------

class ProgressUpdate(BaseModel):
    chapter_number: int
    completion_percentage: float = Field(ge=0.0, le=100.0)


class ReadingProgressOut(BaseModel):
    reader_id: UUID
    publication_id: UUID
    last_chapter_number: int
    completion_percentage: float
    started_at: datetime
    last_read_at: datetime
    completed_at: Optional[datetime]
    is_following: bool

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Ratings
# ---------------------------------------------------------------------------

class RatingSubmit(BaseModel):
    overall: int = Field(ge=1, le=5)
    score_story: Optional[int] = Field(None, ge=1, le=5)
    score_craft: Optional[int] = Field(None, ge=1, le=5)
    score_characters: Optional[int] = Field(None, ge=1, le=5)
    score_pacing: Optional[int] = Field(None, ge=1, le=5)
    score_world: Optional[int] = Field(None, ge=1, le=5)


class RatingOut(BaseModel):
    id: UUID
    reader_id: UUID
    overall: int
    score_story: Optional[int]
    score_craft: Optional[int]
    score_characters: Optional[int]
    score_pacing: Optional[int]
    score_world: Optional[int]
    created_at: datetime

    model_config = {"from_attributes": True}


class RatingAggregate(BaseModel):
    avg_overall: float
    count: int
    avg_story: Optional[float]
    avg_craft: Optional[float]
    avg_characters: Optional[float]
    avg_pacing: Optional[float]
    avg_world: Optional[float]
    distribution: dict  # {1: N, 2: N, 3: N, 4: N, 5: N}


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------

class ReviewSubmit(BaseModel):
    body: str = Field(..., min_length=20, max_length=1000)


class ReviewOut(BaseModel):
    id: UUID
    reader_id: UUID
    body: str
    status: str
    approved_at: Optional[datetime]
    created_at: datetime
    reader_display_name: Optional[str] = None  # joined

    model_config = {"from_attributes": True}


class ReviewAction(BaseModel):
    flagged_reason: Optional[str] = Field(None, max_length=200)


# ---------------------------------------------------------------------------
# Private Notes
# ---------------------------------------------------------------------------

class NoteSubmit(BaseModel):
    chapter_number: Optional[int] = None
    passage_reference: Optional[str] = Field(None, max_length=500)
    body: str = Field(..., min_length=5, max_length=2000)


class NoteReply(BaseModel):
    reply: str = Field(..., min_length=1, max_length=2000)


class PrivateNoteOut(BaseModel):
    id: UUID
    reader_id: UUID
    publication_id: UUID
    chapter_number: Optional[int]
    passage_reference: Optional[str]
    body: str
    writer_reply: Optional[str]
    replied_at: Optional[datetime]
    is_read_by_writer: bool
    created_at: datetime
    reader_display_name: Optional[str] = None  # joined

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# PublicationFollow
# ---------------------------------------------------------------------------

class FollowOut(BaseModel):
    reader_id: UUID
    publication_id: UUID
    followed_at: datetime
    notification_pref: str

    model_config = {"from_attributes": True}


class FollowUpdate(BaseModel):
    notification_pref: str = "immediate"


# ---------------------------------------------------------------------------
# Discovery / Feed
# ---------------------------------------------------------------------------

class DiscoveryFeedResponse(BaseModel):
    items: List[PublicationSummary]
    total: int
    page: int
    per_page: int
    has_more: bool


# ---------------------------------------------------------------------------
# Inbox
# ---------------------------------------------------------------------------

class InboxStats(BaseModel):
    total_views: int
    total_ratings: int
    avg_rating: Optional[float]
    total_reviews: int
    pending_reviews: int
    total_notes: int
    unread_notes: int
    followers: int


class InboxItem(BaseModel):
    kind: str  # "rating" | "review" | "note"
    publication_slug: str
    publication_title: str
    created_at: datetime
    data: dict  # flexible payload depending on kind


class InboxResponse(BaseModel):
    stats: InboxStats
    recent: List[InboxItem]
    pending_reviews: List[ReviewOut]
    unread_notes: List[PrivateNoteOut]
