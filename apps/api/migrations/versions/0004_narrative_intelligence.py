"""narrative intelligence: scene metadata, revelations, weave, voice

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-30
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("scene_cards") as batch:
        batch.add_column(sa.Column("title", sa.String(255), nullable=False, server_default=""))
        batch.add_column(sa.Column("summary", sa.Text, nullable=False, server_default=""))
        batch.add_column(sa.Column("goal", sa.Text, nullable=False, server_default=""))
        batch.add_column(sa.Column("conflict", sa.Text, nullable=False, server_default=""))
        batch.add_column(sa.Column("outcome", sa.Text, nullable=False, server_default=""))
        batch.add_column(sa.Column(
            "pov_character_id",
            sa.String(32),
            sa.ForeignKey("characters.id", ondelete="SET NULL", name="fk_scene_cards_pov_character_id_characters"),
            nullable=True,
        ))
        batch.add_column(sa.Column(
            "location_id",
            sa.String(32),
            sa.ForeignKey("locations.id", ondelete="SET NULL", name="fk_scene_cards_location_id_locations"),
            nullable=True,
        ))
        batch.add_column(sa.Column("character_ids", sa.JSON, nullable=False, server_default="[]"))
        batch.add_column(sa.Column("plot_thread_ids", sa.JSON, nullable=False, server_default="[]"))
        batch.add_column(sa.Column("time_anchor", sa.String(255), nullable=False, server_default=""))
        batch.add_column(sa.Column("time_sort_key", sa.Float, nullable=True))
        batch.add_column(sa.Column("duration_hint", sa.String(120), nullable=False, server_default=""))
        batch.add_column(sa.Column("sensory_palette", sa.JSON, nullable=False, server_default="{}"))
        batch.add_column(sa.Column("source_excerpt", sa.Text, nullable=False, server_default=""))

    op.create_table(
        "revelations",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("story_id", sa.String(32), sa.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scene_id", sa.String(32), sa.ForeignKey("scene_cards.id", ondelete="CASCADE"), nullable=True),
        sa.Column("chapter_id", sa.String(32), sa.ForeignKey("chapters.id", ondelete="CASCADE"), nullable=True),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("kind", sa.String(64), nullable=False, server_default="revelation"),
        sa.Column("characters_who_know", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("reader_knows", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("notes", sa.Text, nullable=False, server_default=""),
        sa.Column("confidence", sa.Float, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_revelations_story_id", "revelations", ["story_id"])

    op.create_table(
        "plot_thread_scene_links",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("story_id", sa.String(32), sa.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("thread_id", sa.String(32), sa.ForeignKey("plot_threads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scene_id", sa.String(32), sa.ForeignKey("scene_cards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_id", sa.String(32), sa.ForeignKey("chapters.id", ondelete="CASCADE"), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="touch"),
        sa.Column("strength", sa.Float, nullable=False, server_default="1"),
        sa.Column("evidence", sa.Text, nullable=False, server_default=""),
        sa.UniqueConstraint("story_id", "thread_id", "scene_id", name="uq_thread_scene_link"),
    )
    op.create_index("ix_plot_thread_scene_links_story_id", "plot_thread_scene_links", ["story_id"])

    op.create_table(
        "character_voice_profiles",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("story_id", sa.String(32), sa.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("character_id", sa.String(32), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sample_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("dialogue_words", sa.Integer, nullable=False, server_default="0"),
        sa.Column("avg_sentence_words", sa.Float, nullable=False, server_default="0"),
        sa.Column("question_rate", sa.Float, nullable=False, server_default="0"),
        sa.Column("exclamation_rate", sa.Float, nullable=False, server_default="0"),
        sa.Column("vocabulary_variety", sa.Float, nullable=False, server_default="0"),
        sa.Column("dialogue_share", sa.Float, nullable=False, server_default="0"),
        sa.Column("repeated_phrases", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("stats", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("story_id", "character_id", name="uq_voice_profile_story_character"),
    )
    op.create_index("ix_character_voice_profiles_story_id", "character_voice_profiles", ["story_id"])


def downgrade() -> None:
    op.drop_table("character_voice_profiles")
    op.drop_table("plot_thread_scene_links")
    op.drop_table("revelations")
    with op.batch_alter_table("scene_cards") as batch:
        for col in (
            "source_excerpt",
            "sensory_palette",
            "duration_hint",
            "time_sort_key",
            "time_anchor",
            "plot_thread_ids",
            "character_ids",
            "location_id",
            "pov_character_id",
            "outcome",
            "conflict",
            "goal",
            "summary",
            "title",
        ):
            batch.drop_column(col)
