"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-28
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "user_llm_settings",
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False, server_default="lmstudio"),
        sa.Column("base_url", sa.String(500), nullable=False, server_default=""),
        sa.Column("model", sa.String(200), nullable=False, server_default=""),
        sa.Column("embed_model", sa.String(200), nullable=False, server_default=""),
        sa.Column("api_key_ciphertext", sa.Text, nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "stories",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False, server_default="Untitled"),
        sa.Column("genre", sa.String(120), nullable=False, server_default=""),
        sa.Column("palette_idx", sa.Integer, nullable=False, server_default="0"),
        sa.Column("graph_status", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_stories_user_id", "stories", ["user_id"])

    op.create_table(
        "worlds",
        sa.Column("story_id", sa.String(32), sa.ForeignKey("stories.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False, server_default=""),
        sa.Column("genre", sa.String(120), nullable=False, server_default=""),
        sa.Column("logline", sa.Text, nullable=False, server_default=""),
        sa.Column("time_period", sa.String(255), nullable=False, server_default=""),
        sa.Column("setting", sa.Text, nullable=False, server_default=""),
        sa.Column("rules", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("themes", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("lore", sa.Text, nullable=False, server_default=""),
        sa.Column("seeds", sa.Text, nullable=False, server_default=""),
    )

    op.create_table(
        "characters",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("story_id", sa.String(32), sa.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(120), nullable=False, server_default=""),
        sa.Column("icon", sa.String(40), nullable=False, server_default=""),
        sa.Column("age", sa.String(64), nullable=False, server_default=""),
        sa.Column("appearance", sa.Text, nullable=False, server_default=""),
        sa.Column("personality", sa.Text, nullable=False, server_default=""),
        sa.Column("backstory", sa.Text, nullable=False, server_default=""),
        sa.Column("motivation", sa.Text, nullable=False, server_default=""),
        sa.Column("flaw", sa.Text, nullable=False, server_default=""),
        sa.Column("arc", sa.Text, nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="alive"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_characters_story_id", "characters", ["story_id"])

    op.create_table(
        "character_relationships",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("story_id", sa.String(32), sa.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", sa.String(32), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_id", sa.String(32), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
    )
    op.create_index("ix_character_relationships_story_id", "character_relationships", ["story_id"])

    op.create_table(
        "locations",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("story_id", sa.String(32), sa.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("visual", sa.Text, nullable=False, server_default=""),
    )
    op.create_index("ix_locations_story_id", "locations", ["story_id"])

    op.create_table(
        "chapters",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("story_id", sa.String(32), sa.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.Integer, nullable=False, server_default="1"),
        sa.Column("title", sa.String(255), nullable=False, server_default=""),
        sa.Column("content", sa.Text, nullable=False, server_default=""),
        sa.Column("summary", sa.Text, nullable=False, server_default=""),
        sa.Column("pov_character_id", sa.String(32), sa.ForeignKey("characters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("location_id", sa.String(32), sa.ForeignKey("locations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("seeds", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("character_ids", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_chapters_story_id", "chapters", ["story_id"])

    op.create_table(
        "factions",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("story_id", sa.String(32), sa.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("visual_signature", sa.Text, nullable=False, server_default=""),
    )
    op.create_index("ix_factions_story_id", "factions", ["story_id"])

    op.create_table(
        "themes",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("story_id", sa.String(32), sa.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.UniqueConstraint("story_id", "name", name="uq_theme_story_name"),
    )
    op.create_index("ix_themes_story_id", "themes", ["story_id"])

    op.create_table(
        "events",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("story_id", sa.String(32), sa.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_id", sa.String(32), sa.ForeignKey("chapters.id", ondelete="CASCADE"), nullable=True),
        sa.Column("kind", sa.String(64), nullable=False, server_default=""),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("involved", sa.JSON, nullable=False, server_default="[]"),
    )
    op.create_index("ix_events_story_id", "events", ["story_id"])

    op.create_table(
        "plot_threads",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("story_id", sa.String(32), sa.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("chapter_ids", sa.JSON, nullable=False, server_default="[]"),
    )
    op.create_index("ix_plot_threads_story_id", "plot_threads", ["story_id"])

    op.create_table(
        "scene_cards",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("story_id", sa.String(32), sa.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_id", sa.String(32), sa.ForeignKey("chapters.id", ondelete="CASCADE"), nullable=True),
        sa.Column("ordinal", sa.Integer, nullable=False, server_default="0"),
        sa.Column("beat", sa.String(120), nullable=False, server_default=""),
        sa.Column("content", sa.Text, nullable=False, server_default=""),
    )
    op.create_index("ix_scene_cards_story_id", "scene_cards", ["story_id"])

    op.create_table(
        "chapter_scripts",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("story_id", sa.String(32), sa.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_id", sa.String(32), sa.ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("panels", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("dialogue", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("visuals", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_chapter_scripts_story_id", "chapter_scripts", ["story_id"])

    op.create_table(
        "flow_drafts",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("story_id", sa.String(32), sa.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("raw", sa.Text, nullable=False, server_default=""),
        sa.Column("polished", sa.Text, nullable=False, server_default=""),
        sa.Column("extracted", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("notes", sa.Text, nullable=False, server_default=""),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_flow_drafts_story_id", "flow_drafts", ["story_id"])

    op.create_table(
        "story_versions",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("story_id", sa.String(32), sa.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_no", sa.Integer, nullable=False),
        sa.Column("snapshot", sa.JSON, nullable=False),
        sa.Column("note", sa.String(255), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("story_id", "version_no", name="uq_story_version"),
    )
    op.create_index("ix_story_versions_story_id", "story_versions", ["story_id"])

    op.create_table(
        "continuity_reports",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("story_id", sa.String(32), sa.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_id", sa.String(32), sa.ForeignKey("chapters.id", ondelete="CASCADE"), nullable=True),
        sa.Column("severity_buckets", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("findings", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("strengths", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_continuity_reports_story_id", "continuity_reports", ["story_id"])

    op.create_table(
        "llm_runs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("story_id", sa.String(32), sa.ForeignKey("stories.id", ondelete="CASCADE"), nullable=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("page", sa.String(120), nullable=False),
        sa.Column("prompt_excerpt", sa.Text, nullable=False, server_default=""),
        sa.Column("response_excerpt", sa.Text, nullable=False, server_default=""),
        sa.Column("tokens_in", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tokens_out", sa.Integer, nullable=False, server_default="0"),
        sa.Column("ms", sa.Float, nullable=False, server_default="0"),
        sa.Column("fallback", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("error", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_llm_runs_user_id", "llm_runs", ["user_id"])
    op.create_index("ix_llm_runs_story_id", "llm_runs", ["story_id"])


def downgrade() -> None:
    for t in [
        "llm_runs", "continuity_reports", "story_versions", "flow_drafts",
        "chapter_scripts", "scene_cards", "plot_threads", "events", "themes",
        "factions", "chapters", "locations", "character_relationships",
        "characters", "worlds", "stories", "user_llm_settings", "users",
    ]:
        op.drop_table(t)
