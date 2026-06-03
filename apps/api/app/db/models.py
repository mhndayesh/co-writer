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
    text,
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
    # Nullable since Clerk-provisioned users have no local password. Legacy
    # password-auth users keep their bcrypt hash here.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Clerk user id (user_xxx) once the account is linked to Clerk. Null for
    # legacy-only accounts that haven't signed in through Clerk yet.
    clerk_user_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    display_name: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    # Subscription / entitlement — denormalized cache for fast per-request checks.
    # Source of truth for billing history is the `subscriptions` table; these two
    # columns are kept in sync by billing_service whenever a subscription changes.
    #   plan_tier:   "free" | "dev_ai" | "byok"   (see app.core.plans.Tier)
    #   plan_status: "none" | "trialing" | "active" | "past_due" | "canceled"
    plan_tier: Mapped[str] = mapped_column(String(32), default="free", server_default="free")
    plan_status: Mapped[str] = mapped_column(String(32), default="none", server_default="none")
    # HARD expiry for a non-auto-renewing grant (promo code / manual). NULL = no
    # expiry (lifetime grant, or an auto-renewing Stripe sub whose lapse is handled
    # by webhooks). entitlement_service lapses a paid tier to free once this passes.
    plan_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))

    # Session epoch. Bumped on logout / password change to invalidate every
    # outstanding access token (each access JWT carries the `tv` it was minted
    # with; get_current_user rejects a mismatch). See app.services.auth_service.
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # Owner-only "shape-shift": when set on an owner, their effective entitlement
    # AND provider routing simulate this tier so they can test the real experience
    # of each user type. One of "free" | "dev_ai" | "byok" | None (None / "owner"
    # = real unlimited owner). Read only when is_owner(user); rejected at write for
    # everyone else, so a stray value on a normal user has no effect.
    act_as_tier: Mapped[str | None] = mapped_column(String(16), nullable=True)


class RefreshToken(Base):
    """One row per issued refresh token (by `jti`). Enables rotation, revocation,
    and refresh-token-reuse detection — a stateless JWT alone can't be revoked.

    On /refresh the presented row is marked revoked and a new one minted
    (`replaced_by`). Presenting an already-revoked token = theft → the whole
    family is revoked and the user's token_version bumped."""

    __tablename__ = "refresh_tokens"

    jti: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    replaced_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Subscription(Base):
    """One billing subscription record. Provider-agnostic: `provider` names the
    payment backend ("manual", "stripe", …) and the `external_*` columns hold
    whatever ids that backend issued. The user's *current* tier/status is mirrored
    onto `users.plan_tier`/`plan_status` by billing_service for cheap reads."""

    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(32), default="manual")
    tier: Mapped[str] = mapped_column(String(32))           # "dev_ai" | "byok"
    status: Mapped[str] = mapped_column(String(32), default="active")
    external_customer_id: Mapped[str] = mapped_column(String(255), default="")
    external_subscription_id: Mapped[str] = mapped_column(String(255), default="", index=True)
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    raw: Mapped[dict] = mapped_column(JSON, default=dict)   # last provider payload snapshot
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class BillingEventRecord(Base):
    """Idempotency ledger for inbound provider webhooks. The (provider,
    external_event_id) unique constraint makes webhook processing exactly-once:
    Stripe delivers at-least-once and retries, so the route inserts this row
    first and skips any event whose id is already recorded."""

    __tablename__ = "billing_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    provider: Mapped[str] = mapped_column(String(32))
    external_event_id: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        UniqueConstraint("provider", "external_event_id", name="uq_billing_event"),
    )


class RedemptionCode(Base):
    """An owner-minted promo / gift code that grants a paid tier for a period when
    redeemed. Free subscriptions handed out manually — no payment involved."""

    __tablename__ = "redemption_codes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # stored uppercased
    tier: Mapped[str] = mapped_column(String(32))                # "dev_ai" | "byok"
    # Subscription length granted on redeem. NULL = lifetime (no expiry).
    duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)  # NULL = unlimited
    uses: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    note: Mapped[str] = mapped_column(String(200), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # code redeemable-until
    created_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class CodeRedemption(Base):
    """One row per (code, user) — enforces one redemption per user per code."""

    __tablename__ = "code_redemptions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    code_id: Mapped[str] = mapped_column(String(32), ForeignKey("redemption_codes.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    tier: Mapped[str] = mapped_column(String(32))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    redeemed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        UniqueConstraint("code_id", "user_id", name="uq_code_redemption_per_user"),
    )


class IdempotencyKey(Base):
    """Dedupe ledger for client-initiated mutations that aren't naturally
    idempotent (Flow approve, publish push). The client sends an `Idempotency-Key`
    header per logical operation; the server records (user_id, scope, key) with the
    original response and replays it verbatim if the same key arrives again — so a
    retry on a flaky connection can't double-commit a chapter or chapter version.

    `scope` namespaces the key by operation + resource (e.g. "flow.approve:<story_id>")
    so an unrelated operation can't collide with a reused key."""

    __tablename__ = "idempotency_keys"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    scope: Mapped[str] = mapped_column(String(120))
    idem_key: Mapped[str] = mapped_column(String(128))
    response: Mapped[dict] = mapped_column(JSON, default=dict)  # the original envelope `data`
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        UniqueConstraint("user_id", "scope", "idem_key", name="uq_idempotency_key"),
    )


class UserLLMSettings(Base):
    __tablename__ = "user_llm_settings"

    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    # Three routing lanes — creative | technical | embedding — each a dict:
    # {provider, base_url, model, embed_model, api_key_ciphertext}.
    # "Use one model for everything" = all three lanes set identically.
    lanes: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Story(Base):
    __tablename__ = "stories"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255), default="Untitled")
    genre: Mapped[str] = mapped_column(String(120), default="")
    palette_idx: Mapped[int] = mapped_column(Integer, default=0)
    cover_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)  # uploaded path or http(s) URL
    graph_status: Mapped[str] = mapped_column(String(32), default="unknown")  # unknown|ok|unavailable
    # When the Neo4j projection last succeeded. NULL = never synced. A background
    # reconciler (graph_service.reconcile_stale_graphs) retries any story whose
    # graph_status != "ok" so a Neo4j outage during approve self-heals later.
    graph_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
    # Optimistic-concurrency token: SQLAlchemy adds `WHERE version_id=:old` to every
    # ORM UPDATE and bumps it; a concurrent read-modify-write loses → StaleDataError
    # (mapped to 409). Stops two tabs silently clobbering each other's edits.
    version_id: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    story: Mapped[Story] = relationship("Story", back_populates="characters")
    relationships_out: Mapped[list[CharacterRelationship]] = relationship(
        "CharacterRelationship",
        foreign_keys="CharacterRelationship.source_id",
        cascade="all, delete-orphan",
        back_populates="source",
    )

    __mapper_args__ = {"version_id_col": version_id}


class CharacterRelationship(Base):
    __tablename__ = "character_relationships"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    story_id: Mapped[str] = mapped_column(String(32), ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[str] = mapped_column(String(32), ForeignKey("characters.id", ondelete="CASCADE"))
    target_id: Mapped[str] = mapped_column(String(32), ForeignKey("characters.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(64))  # ally|enemy|lover|rival|family|...
    description: Mapped[str] = mapped_column(Text, default="")

    source: Mapped[Character] = relationship("Character", foreign_keys=[source_id], back_populates="relationships_out")

    # The documented invariant is one row per (source,target) — approve() already
    # updates in place, but the manual POST route could create duplicate edges.
    __table_args__ = (
        UniqueConstraint("story_id", "source_id", "target_id", name="uq_character_relationship_pair"),
    )


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    story_id: Mapped[str] = mapped_column(String(32), ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(255), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    cover_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)  # optional per-chapter cover
    pov_character_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("characters.id", ondelete="SET NULL"), nullable=True)
    location_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("locations.id", ondelete="SET NULL"), nullable=True)
    seeds: Mapped[list[Any]] = mapped_column(JSON, default=list)
    character_ids: Mapped[list[str]] = mapped_column(JSON, default=list)  # denormalized for fast read
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    # Optimistic-concurrency token (see Character.version_id) — most valuable here:
    # chapter.content is the field two tabs are most likely to clobber.
    version_id: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    story: Mapped[Story] = relationship("Story", back_populates="chapters")

    __mapper_args__ = {"version_id_col": version_id}


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
    title: Mapped[str] = mapped_column(String(255), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    goal: Mapped[str] = mapped_column(Text, default="")
    conflict: Mapped[str] = mapped_column(Text, default="")
    outcome: Mapped[str] = mapped_column(Text, default="")
    pov_character_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("characters.id", ondelete="SET NULL"), nullable=True)
    location_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("locations.id", ondelete="SET NULL"), nullable=True)
    character_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    plot_thread_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    time_anchor: Mapped[str] = mapped_column(String(255), default="")
    time_sort_key: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_hint: Mapped[str] = mapped_column(String(120), default="")
    sensory_palette: Mapped[dict] = mapped_column(JSON, default=dict)
    source_excerpt: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text, default="")
    # Optimistic-concurrency token (see Character.version_id).
    version_id: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    __mapper_args__ = {"version_id_col": version_id}


class Revelation(Base):
    __tablename__ = "revelations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    story_id: Mapped[str] = mapped_column(String(32), ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    scene_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("scene_cards.id", ondelete="CASCADE"), nullable=True)
    chapter_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("chapters.id", ondelete="CASCADE"), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(64), default="revelation")
    characters_who_know: Mapped[list[str]] = mapped_column(JSON, default=list)
    reader_knows: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PlotThreadSceneLink(Base):
    __tablename__ = "plot_thread_scene_links"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    story_id: Mapped[str] = mapped_column(String(32), ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    thread_id: Mapped[str] = mapped_column(String(32), ForeignKey("plot_threads.id", ondelete="CASCADE"))
    scene_id: Mapped[str] = mapped_column(String(32), ForeignKey("scene_cards.id", ondelete="CASCADE"))
    chapter_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("chapters.id", ondelete="CASCADE"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="touch")  # touch|setup|turn|payoff
    strength: Mapped[float] = mapped_column(Float, default=1.0)
    evidence: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (UniqueConstraint("story_id", "thread_id", "scene_id", name="uq_thread_scene_link"),)


class CharacterVoiceProfile(Base):
    __tablename__ = "character_voice_profiles"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    story_id: Mapped[str] = mapped_column(String(32), ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    character_id: Mapped[str] = mapped_column(String(32), ForeignKey("characters.id", ondelete="CASCADE"))
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    dialogue_words: Mapped[int] = mapped_column(Integer, default=0)
    avg_sentence_words: Mapped[float] = mapped_column(Float, default=0.0)
    question_rate: Mapped[float] = mapped_column(Float, default=0.0)
    exclamation_rate: Mapped[float] = mapped_column(Float, default=0.0)
    vocabulary_variety: Mapped[float] = mapped_column(Float, default=0.0)
    dialogue_share: Mapped[float] = mapped_column(Float, default=0.0)
    repeated_phrases: Mapped[list[str]] = mapped_column(JSON, default=list)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    __table_args__ = (UniqueConstraint("story_id", "character_id", name="uq_voice_profile_story_character"),)


# ── Character Voice Studio (Narrative Fidelity Engine) ─────────────────────────
# A layer ABOVE the Story Engine: how the story FEELS on the page (voice, behavior,
# atmosphere). The legacy free-text Character columns (personality/backstory/…) stay
# the context-read source; these tables are the rich authoring surface that compiles
# down into them. The deterministic numeric voice stats stay in CharacterVoiceProfile
# (above) — `CharacterIdentity.voice_fingerprint` holds only qualitative descriptors.

class CharacterIdentity(Base):
    """Layers 1-3 of the identity model (1:1 with Character). Each layer is a JSON
    blob, edited as a unit (same idiom as World). Masks (layer 4) and States
    (layer 5) are separate tables because they have natural multiplicity."""
    __tablename__ = "character_identities"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    story_id: Mapped[str] = mapped_column(String(32), ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    character_id: Mapped[str] = mapped_column(String(32), ForeignKey("characters.id", ondelete="CASCADE"))
    # worldview, values, ambitions, fears, insecurities, contradictions,
    # emotional_weaknesses, coping, hides_from_others, refuses_to_admit
    core_personality: Mapped[dict] = mapped_column(JSON, default=dict)
    # under_stress, physical_habits, reaction_to_authority, reaction_to_intimacy,
    # when_lying, with_strangers, with_close, loses_control_when
    behavioral_patterns: Mapped[dict] = mapped_column(JSON, default=dict)
    # QUALITATIVE half only — sentence_length, vocab_complexity, slang_level,
    # contractions, directness, emotional_openness, humor_style, metaphor_use,
    # profanity, asks_vs_states, interrupts, repeated_phrases[], avoided_words[],
    # shifts:{angry,frightened,relaxed,with_authority}
    voice_fingerprint: Mapped[dict] = mapped_column(JSON, default=dict)
    short_profile: Mapped[str] = mapped_column(Text, default="")     # readable synthesized summary
    build_method: Mapped[str] = mapped_column(String(32), default="")  # interview|analyze|manual|""
    completeness: Mapped[dict] = mapped_column(JSON, default=dict)    # {core,behavioral,voice} 0-100 for UI
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    __table_args__ = (UniqueConstraint("story_id", "character_id", name="uq_identity_story_character"),)


class RelationshipMask(Base):
    """Layer 4 — how the speaker's VOICE changes per audience. Distinct from
    CharacterRelationship (which is a bond type+description). Audience can be a
    specific cast member or a role-class label ("police", "a client")."""
    __tablename__ = "relationship_masks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    story_id: Mapped[str] = mapped_column(String(32), ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    character_id: Mapped[str] = mapped_column(String(32), ForeignKey("characters.id", ondelete="CASCADE"))  # speaker
    audience_character_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("characters.id", ondelete="SET NULL"), nullable=True)
    audience_label: Mapped[str] = mapped_column(String(120), default="")  # used when audience is a role-class
    speech_style: Mapped[str] = mapped_column(Text, default="")
    tells: Mapped[str] = mapped_column(Text, default="")          # what leaks through the mask
    notes: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class CharacterState(Base):
    """Layer 5 — temporary, scene-scoped condition. `kind` encodes the post-scene
    save-as decision (temporary reaction / recurring response / arc development)."""
    __tablename__ = "character_states"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    story_id: Mapped[str] = mapped_column(String(32), ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    character_id: Mapped[str] = mapped_column(String(32), ForeignKey("characters.id", ondelete="CASCADE"))
    chapter_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    label: Mapped[str] = mapped_column(String(120), default="")   # "injured","grieving","gaining confidence"
    detail: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(24), default="temporary")  # temporary|recurring|arc
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class PlaceIdentity(Base):
    """Part 1C — rich identity for a Location (1:1). Lighter than character identity;
    edited as a unit, so JSON-in-1:1-table like World."""
    __tablename__ = "place_identities"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    story_id: Mapped[str] = mapped_column(String(32), ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    location_id: Mapped[str] = mapped_column(String(32), ForeignKey("locations.id", ondelete="CASCADE"))
    purpose: Mapped[str] = mapped_column(Text, default="")
    atmosphere: Mapped[str] = mapped_column(Text, default="")
    sensory_palette: Mapped[dict] = mapped_column(JSON, default=dict)   # {sound,smell,lighting,temperature,textures}
    visual_anchors: Mapped[list[Any]] = mapped_column(JSON, default=list)
    spatial_layout: Mapped[str] = mapped_column(Text, default="")
    controls_space: Mapped[str] = mapped_column(String(255), default="")
    social_rules: Mapped[str] = mapped_column(Text, default="")
    normal_behavior: Mapped[str] = mapped_column(Text, default="")
    variations: Mapped[dict] = mapped_column(JSON, default=dict)        # {time,weather,phase}
    symbolic_motif: Mapped[str] = mapped_column(String(255), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    __table_args__ = (UniqueConstraint("story_id", "location_id", name="uq_place_identity_location"),)


class VoiceException(Base):
    """"Mark as intentional" persistence. The Observer computes the same `fingerprint`
    for each candidate note and drops any whose fingerprint matches a stored row, so
    a deliberate deviation stops being re-flagged (until the line is really rewritten)."""
    __tablename__ = "voice_exceptions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    story_id: Mapped[str] = mapped_column(String(32), ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    chapter_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    character_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("characters.id", ondelete="SET NULL"), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)  # hash(character_id + normalized_line + note_kind)
    line_excerpt: Mapped[str] = mapped_column(Text, default="")
    note_kind: Mapped[str] = mapped_column(String(64), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (UniqueConstraint("story_id", "fingerprint", name="uq_voice_exception"),)


class IdentityVersion(Base):
    """Append-only history. Covers both "version everything" and "arc progression
    over time" (filter kind='arc'). Snapshots the CHANGED layer only (not the whole
    identity) and is pruned per (character, kind) to bound growth — same spirit as
    the _MAX_*_CTX caps in context_builder."""
    __tablename__ = "identity_versions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    story_id: Mapped[str] = mapped_column(String(32), ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    character_id: Mapped[str] = mapped_column(String(32), ForeignKey("characters.id", ondelete="CASCADE"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    # core|inferred|approved_canon|scene_state|relationship_mask|arc|intentional_exception
    kind: Mapped[str] = mapped_column(String(32))
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    note: Mapped[str] = mapped_column(String(255), default="")
    chapter_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (UniqueConstraint("story_id", "character_id", "version_no", name="uq_identity_version"),)


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


from app.db.publishing_models import (  # noqa: F401, E402
    Publication, PublicationChapter, ReaderProfile,
    ReadingProgress, StoryRating, Review, PrivateNote, PublicationFollow,
)


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
    # Which key paid for this call — the unit the usage meter counts.
    #   "server" → website's house ("dev AI") key (free trial + dev_ai tier)
    #   "user"   → the user's own BYOK key (not metered)
    #   "none"   → fallback/degraded or unbilled diagnostic (not metered)
    key_source: Mapped[str] = mapped_column(String(16), default="none", server_default="none", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SiteSettings(Base):
    """Owner-managed, site-wide configuration. Single row (id='singleton').

    Holds the "house" / default AI that every free + dev_ai (house-key) user runs
    on, plus the tunable usage caps for those tiers. A NULL/blank column falls
    back to the env default in app.core.config (so an unconfigured deploy behaves
    exactly as before). Edited only by the owner via /v1/admin/site-config."""

    __tablename__ = "site_settings"

    id: Mapped[str] = mapped_column(String(16), primary_key=True, default="singleton")

    # House default provider. When house_provider is NULL, fall back to
    # settings.system_llm_provider (env). Key encrypted at rest (Fernet).
    house_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    house_base_url: Mapped[str] = mapped_column(String(512), default="", server_default="")
    house_model: Mapped[str] = mapped_column(String(200), default="", server_default="")
    house_embed_model: Mapped[str] = mapped_column(String(200), default="", server_default="")
    house_api_key_ciphertext: Mapped[str] = mapped_column(Text, default="", server_default="")

    # Tunable caps. NULL = use the env default (not "unlimited" — unlimited is
    # tier-driven). Apply only on the metered house-key path (free / dev_ai).
    dev_ai_max_actions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dev_ai_max_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    free_trial_max_actions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    free_trial_max_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
