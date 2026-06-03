# apps/api/app/db/publishing_models.py
#
# Publishing platform SQLAlchemy models.
# All PKs/FKs use String(32) hex UUIDs to match the existing app convention.
# Import these at the bottom of app/db/models.py:
#   from app.db.publishing_models import *  # noqa

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, ForeignKey,
    Index, Integer, JSON, SmallInteger, String, Text, UniqueConstraint, text,
)
from sqlalchemy.orm import relationship

from app.db.base import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.utcnow()


# ---------------------------------------------------------------------------
# Enums  (native on PostgreSQL, VARCHAR fallback on SQLite)
# ---------------------------------------------------------------------------

PublicationStatus = Enum(
    "draft", "published", "unlisted", "archived",
    name="publication_status",
)

ReleaseType = Enum(
    "complete", "serial",
    name="release_type",
)

ReviewStatus = Enum(
    "pending", "approved", "declined", "flagged",
    name="review_status",
)

NotificationPref = Enum(
    "immediate", "digest", "none",
    name="notification_pref",
)


# ---------------------------------------------------------------------------
# Publication  (public record of a story)
# ---------------------------------------------------------------------------

class Publication(Base):
    __tablename__ = "publications"

    id       = Column(String(32), primary_key=True, default=_uuid)
    story_id = Column(String(32), ForeignKey("stories.id", ondelete="CASCADE"), nullable=False, unique=True)
    user_id  = Column(String(32), ForeignKey("users.id",   ondelete="CASCADE"), nullable=False, index=True)

    slug            = Column(String(200), nullable=False, unique=True, index=True)
    status          = Column(String(20),  nullable=False, default="draft")
    release_type    = Column(String(20),  nullable=False, default="complete")
    cover_image_url = Column(Text, nullable=True)
    tagline         = Column(String(300), nullable=True)
    content_warnings = Column(JSON, nullable=False, default=list)
    genre           = Column(String(60), nullable=True)
    tags            = Column(JSON, nullable=False, default=list)

    published_at           = Column(DateTime, nullable=True)
    last_chapter_pushed_at = Column(DateTime, nullable=True)
    total_planned_chapters = Column(Integer, nullable=True)

    view_count = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime, nullable=False, default=_now)
    updated_at = Column(DateTime, nullable=False, default=_now, onupdate=_now)

    pub_chapters  = relationship("PublicationChapter", back_populates="publication", cascade="all, delete-orphan")
    ratings       = relationship("StoryRating",        back_populates="publication", cascade="all, delete-orphan")
    reviews       = relationship("Review",             back_populates="publication", cascade="all, delete-orphan")
    private_notes = relationship("PrivateNote",        back_populates="publication", cascade="all, delete-orphan")
    follows       = relationship("PublicationFollow",  back_populates="publication", cascade="all, delete-orphan")
    progress_rows = relationship("ReadingProgress",    back_populates="publication", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# PublicationChapter  (immutable snapshot of a pushed chapter)
# ---------------------------------------------------------------------------

class PublicationChapter(Base):
    __tablename__ = "publication_chapters"

    id             = Column(String(32), primary_key=True, default=_uuid)
    publication_id = Column(String(32), ForeignKey("publications.id", ondelete="CASCADE"), nullable=False, index=True)
    chapter_number = Column(Integer, nullable=False)
    version        = Column(Integer, nullable=False, default=1)
    title          = Column(String(300), nullable=False)
    content        = Column(Text, nullable=False)
    word_count     = Column(Integer, nullable=False, default=0)
    pushed_at      = Column(DateTime, nullable=False, default=_now)
    is_latest      = Column(Boolean, nullable=False, default=True)

    publication = relationship("Publication", back_populates="pub_chapters")

    __table_args__ = (
        # Partial unique index: only ONE "is_latest=True" row is allowed per
        # (publication_id, chapter_number). Old versions (is_latest=False) are
        # unconstrained so the same chapter can be re-pushed many times.
        Index(
            "uq_pub_chapter_latest",
            "publication_id",
            "chapter_number",
            unique=True,
            postgresql_where=text("is_latest = TRUE"),
            sqlite_where=text("is_latest = 1"),
        ),
    )


# ---------------------------------------------------------------------------
# ReaderProfile
# ---------------------------------------------------------------------------

class ReaderProfile(Base):
    __tablename__ = "reader_profiles"

    user_id      = Column(String(32), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    display_name = Column(String(80), nullable=True)
    bio          = Column(String(500), nullable=True)
    avatar_url   = Column(Text, nullable=True)
    is_age_verified = Column(Boolean, nullable=False, default=False)
    profile_public  = Column(Boolean, nullable=False, default=True, server_default=text("1"))
    created_at   = Column(DateTime, nullable=False, default=_now)


# ---------------------------------------------------------------------------
# ReadingProgress
# ---------------------------------------------------------------------------

class ReadingProgress(Base):
    __tablename__ = "reading_progress"

    id             = Column(String(32), primary_key=True, default=_uuid)
    reader_id      = Column(String(32), ForeignKey("users.id",        ondelete="CASCADE"), nullable=False, index=True)
    publication_id = Column(String(32), ForeignKey("publications.id", ondelete="CASCADE"), nullable=False, index=True)

    last_chapter_number   = Column(Integer, nullable=False, default=0)
    completion_percentage = Column(Float,   nullable=False, default=0.0)

    started_at   = Column(DateTime, nullable=False, default=_now)
    last_read_at = Column(DateTime, nullable=False, default=_now, onupdate=_now)
    completed_at = Column(DateTime, nullable=True)
    is_following = Column(Boolean, nullable=False, default=False)

    publication = relationship("Publication", back_populates="progress_rows")

    __table_args__ = (
        UniqueConstraint("reader_id", "publication_id", name="uq_reading_progress"),
    )


# ---------------------------------------------------------------------------
# StoryRating
# ---------------------------------------------------------------------------

class StoryRating(Base):
    __tablename__ = "story_ratings"

    id             = Column(String(32), primary_key=True, default=_uuid)
    reader_id      = Column(String(32), ForeignKey("users.id",        ondelete="CASCADE"), nullable=False)
    publication_id = Column(String(32), ForeignKey("publications.id", ondelete="CASCADE"), nullable=False, index=True)

    overall           = Column(SmallInteger, nullable=False)
    score_story       = Column(SmallInteger, nullable=True)
    score_craft       = Column(SmallInteger, nullable=True)
    score_characters  = Column(SmallInteger, nullable=True)
    score_pacing      = Column(SmallInteger, nullable=True)
    score_world       = Column(SmallInteger, nullable=True)

    created_at = Column(DateTime, nullable=False, default=_now)
    updated_at = Column(DateTime, nullable=False, default=_now, onupdate=_now)

    publication = relationship("Publication", back_populates="ratings")

    __table_args__ = (
        UniqueConstraint("reader_id", "publication_id", name="uq_story_rating"),
    )


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------

class Review(Base):
    __tablename__ = "reviews"

    id             = Column(String(32), primary_key=True, default=_uuid)
    reader_id      = Column(String(32), ForeignKey("users.id",        ondelete="CASCADE"), nullable=False)
    publication_id = Column(String(32), ForeignKey("publications.id", ondelete="CASCADE"), nullable=False)

    body           = Column(Text, nullable=False)
    status         = Column(String(20), nullable=False, default="pending")
    flagged_reason = Column(String(200), nullable=True)
    approved_at    = Column(DateTime, nullable=True)
    created_at     = Column(DateTime, nullable=False, default=_now)

    publication = relationship("Publication", back_populates="reviews")

    __table_args__ = (
        UniqueConstraint("reader_id", "publication_id", name="uq_review"),
    )


# ---------------------------------------------------------------------------
# PrivateNote
# ---------------------------------------------------------------------------

class PrivateNote(Base):
    __tablename__ = "private_notes"

    id             = Column(String(32), primary_key=True, default=_uuid)
    reader_id      = Column(String(32), ForeignKey("users.id",        ondelete="CASCADE"), nullable=False, index=True)
    publication_id = Column(String(32), ForeignKey("publications.id", ondelete="CASCADE"), nullable=False, index=True)

    chapter_number    = Column(Integer, nullable=True)
    passage_reference = Column(String(500), nullable=True)
    body              = Column(Text, nullable=False)

    writer_reply      = Column(Text, nullable=True)
    replied_at        = Column(DateTime, nullable=True)
    is_read_by_writer = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime, nullable=False, default=_now)

    publication = relationship("Publication", back_populates="private_notes")


# ---------------------------------------------------------------------------
# PublicationFollow
# ---------------------------------------------------------------------------

class PublicationFollow(Base):
    __tablename__ = "publication_follows"

    reader_id      = Column(String(32), ForeignKey("users.id",        ondelete="CASCADE"), primary_key=True)
    publication_id = Column(String(32), ForeignKey("publications.id", ondelete="CASCADE"), primary_key=True, index=True)

    followed_at       = Column(DateTime, nullable=False, default=_now)
    notification_pref = Column(String(20), nullable=False, default="immediate")

    publication = relationship("Publication", back_populates="follows")


# ---------------------------------------------------------------------------
# Notification  (in-app; email delivery is a later add-on)
# ---------------------------------------------------------------------------

class Notification(Base):
    __tablename__ = "notifications"

    id      = Column(String(32), primary_key=True, default=_uuid)
    user_id = Column(String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)  # recipient
    kind    = Column(String(32), nullable=False, default="new_chapter")
    publication_id = Column(String(32), ForeignKey("publications.id", ondelete="CASCADE"), nullable=True, index=True)
    title   = Column(String(300), nullable=False, default="")
    body    = Column(Text, nullable=False, default="")
    link    = Column(Text, nullable=True)  # reader URL to open (e.g. /read/<slug>/<n>)
    read    = Column(Boolean, nullable=False, default=False, server_default=text("0"))
    created_at = Column(DateTime, nullable=False, default=_now, index=True)

    __table_args__ = (
        Index("ix_notifications_user_read", "user_id", "read"),
    )
