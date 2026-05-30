"""SQLAlchemy ORM models for G-Ink Novel Studio.

Schema mirrors the data model in Story_Forge_Docs.md §6 plus production-stage
entities (scenes, threads, scripts) and bookkeeping tables (versions, llm_runs).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class UserLLMSettings(Base):
    __tablename__ = "user_llm_settings"

    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    # Routing mode: single | split | custom. The flat columns below are the
    # "default" profile — used in single mode and as the universal fallback.
    mode: Mapped[str] = mapped_column(String(16), default="single")
    provider: Mapped[str] = mapped_column(String(32), default="lmstudio")
    base_url: Mapped[str] = mapped_column(String(500), default="")
    model: Mapped[str] = mapped_column(String(200), default="")
    embed_model: Mapped[str] = mapped_column(String(200), default="")
    api_key_ciphertext: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class LLMProfile(Base):
    """A per-role provider config beyond the default in UserLLMSettings.

    role ∈ "creative" | "technical" | "embedding" | "task:<page>"
    (e.g. "task:flow.polish"). One row per (user, role).
    """
    __tablename__ = "llm_profiles"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(32), default="lmstudio")
    base_url: Mapped[str] = mapped_column(String(500), default="")
    model: Mapped[str] = mapped_column(String(200), default="")
    embed_model: Mapped[str] = mapped_column(String(200), default="")
    api_key_ciphertext: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    __table_args__ = (UniqueConstraint("user_id", "role", name="uq_llm_profile_user_role"),)


class Story(Base):
    __tablename__ = "stories"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255), default="Untitled")
    genre: Mapped[str] = mapped_column(String(120), default="")
    palette_idx: Mapped[int] = mapped_column(Integer, default=0)
    graph_status: Mapped[str] = mapped_column(String(32), default="unknown")  # unknown|ok|unavailable
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    world: Mapped[World | None] = relationship("World", back_populates="story", uselist=False, cascade="all, delete-orphan")
    characters: Mapped[list[Character]] = relationship("Character", back_populates="story", cascade="all, delete-orphan")
    chapters: Mapped[list[Chapter]] = relationship("Chapter", back_populates="story", cascade="all, delete-orphan")


class World(Base):
    __tablename__ = "worlds"

    story_id: Mapped[str] = mapped_column(String(32), ForeignKey("stories.id", ondelete="CASCADE"), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    genre: Mapped[str] = mapped_column(String(120), default="")
    logline: Mapped[str] = mapped_column(Text, default="")
    time_period: Mapped[str] = mapped_column(String(255), default="")
    setting: Mapped[str] = mapped_column(Text, default="")
    rules: Mapped[list[str]] = mapped_column(JSON, default=list)
    themes: Mapped[list[str]] = mapped_column(JSON, default=list)
    lore: Mapped[str] = mapped_column(Text, default="")
    seeds: Mapped[str] = mapped_column(Text, default="")

    story: Mapped[Story] = relationship("Story", back_populates="world")


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    story_id: Mapped[str] = mapped_column(String(32), ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(120), default="")
    icon: Mapped[str] = mapped_column(String(40), default="")
    age: Mapped[str] = mapped_column(String(64), default="")
    appearance: Mapped[str] = mapped_column(Text, default="")
    personality: Mapped[str] = mapped_column(Text, default="")
    backstory: Mapped[str] = mapped_column(Text, default="")
    motivation: Mapped[str] = mapped_column(Text, default="")
    flaw: Mapped[str] = mapped_column(Text, default="")
    arc: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="alive")  # alive|dead|unknown|missing|transformed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    story: Mapped[Story] = relationship("Story", back_populates="characters")
    relationships_out: Mapped[list[CharacterRelationship]] = relationship(
        "CharacterRelationship",
        foreign_keys="CharacterRelationship.source_id",
        cascade="all, delete-orphan",
        back_populates="source",
    )


class CharacterRelationship(Base):
    __tablename__ = "character_relationships"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    story_id: Mapped[str] = mapped_column(String(32), ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[str] = mapped_column(String(32), ForeignKey("characters.id", ondelete="CASCADE"))
    target_id: Mapped[str] = mapped_column(String(32), ForeignKey("characters.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(64))  # ally|enemy|lover|rival|family|...
    description: Mapped[str] = mapped_column(Text, default="")

    source: Mapped[Character] = relationship("Character", foreign_keys=[source_id], back_populates="relationships_out")


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    story_id: Mapped[str] = mapped_column(String(32), ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(255), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    pov_character_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("characters.id", ondelete="SET NULL"), nullable=True)
    location_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("locations.id", ondelete="SET NULL"), nullable=True)
    seeds: Mapped[list[Any]] = mapped_column(JSON, default=list)
    character_ids: Mapped[list[str]] = mapped_column(JSON, default=list)  # denormalized for fast read
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    story: Mapped[Story] = relationship("Story", back_populates="chapters")


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    story_id: Mapped[str] = mapped_column(String(32), ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    visual: Mapped[str] = mapped_column(Text, default="")


class Faction(Base):
    __tablename__ = "factions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    story_id: Mapped[str] = mapped_column(String(32), ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    visual_signature: Mapped[str] = mapped_column(Text, default="")


class Theme(Base):
    __tablename__ = "themes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    story_id: Mapped[str] = mapped_column(String(32), ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (UniqueConstraint("story_id", "name", name="uq_theme_story_name"),)


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    story_id: Mapped[str] = mapped_column(String(32), ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    chapter_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("chapters.id", ondelete="CASCADE"), nullable=True)
    kind: Mapped[str] = mapped_column(String(64), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    involved: Mapped[list[str]] = mapped_column(JSON, default=list)


class PlotThread(Base):
    __tablename__ = "plot_threads"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    story_id: Mapped[str] = mapped_column(String(32), ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="open")  # open|paid_off|abandoned
    description: Mapped[str] = mapped_column(Text, default="")
    chapter_ids: Mapped[list[str]] = mapped_column(JSON, default=list)


class SceneCard(Base):
    __tablename__ = "scene_cards"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    story_id: Mapped[str] = mapped_column(String(32), ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    chapter_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("chapters.id", ondelete="CASCADE"), nullable=True)
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    beat: Mapped[str] = mapped_column(String(120), default="")
    content: Mapped[str] = mapped_column(Text, default="")


class ChapterScript(Base):
    __tablename__ = "chapter_scripts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    story_id: Mapped[str] = mapped_column(String(32), ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    chapter_id: Mapped[str] = mapped_column(String(32), ForeignKey("chapters.id", ondelete="CASCADE"))
    panels: Mapped[list[Any]] = mapped_column(JSON, default=list)
    dialogue: Mapped[list[Any]] = mapped_column(JSON, default=list)
    visuals: Mapped[list[Any]] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class FlowDraft(Base):
    __tablename__ = "flow_drafts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    story_id: Mapped[str] = mapped_column(String(32), ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    raw: Mapped[str] = mapped_column(Text, default="")
    polished: Mapped[str] = mapped_column(Text, default="")
    extracted: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[str] = mapped_column(Text, default="")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class StoryVersion(Base):
    __tablename__ = "story_versions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    story_id: Mapped[str] = mapped_column(String(32), ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON)
    note: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (UniqueConstraint("story_id", "version_no", name="uq_story_version"),)


class ContinuityReport(Base):
    __tablename__ = "continuity_reports"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    story_id: Mapped[str] = mapped_column(String(32), ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    chapter_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("chapters.id", ondelete="CASCADE"), nullable=True)
    severity_buckets: Mapped[dict] = mapped_column(JSON, default=dict)
    findings: Mapped[list[Any]] = mapped_column(JSON, default=list)
    strengths: Mapped[list[Any]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class LLMRun(Base):
    __tablename__ = "llm_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    story_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("stories.id", ondelete="CASCADE"), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(200))
    page: Mapped[str] = mapped_column(String(120))
    prompt_excerpt: Mapped[str] = mapped_column(Text, default="")
    response_excerpt: Mapped[str] = mapped_column(Text, default="")
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    ms: Mapped[float] = mapped_column(Float, default=0.0)
    fallback: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
