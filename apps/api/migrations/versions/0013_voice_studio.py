"""Character Voice Studio (Narrative Fidelity Engine)

Additive only — six new tables, no changes to existing ones. The legacy free-text
Character columns stay the context-read source; these tables are the rich authoring
surface that compiles down into them.

1. character_identities — identity layers 1-3 (core / behavioral / voice fingerprint), 1:1 w/ Character
2. relationship_masks  — layer 4: per-audience speech style
3. character_states    — layer 5: scene-scoped temporary condition
4. place_identities     — Part 1C: rich Location identity, 1:1 w/ Location
5. voice_exceptions     — "mark as intentional" memory so notes stop re-flagging
6. identity_versions    — append-only history + arc progression timeline
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "character_identities",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("story_id", sa.String(32), sa.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("character_id", sa.String(32), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("core_personality", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("behavioral_patterns", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("voice_fingerprint", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("short_profile", sa.Text(), nullable=False, server_default=""),
        sa.Column("build_method", sa.String(32), nullable=False, server_default=""),
        sa.Column("completeness", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("story_id", "character_id", name="uq_identity_story_character"),
    )
    op.create_index("ix_character_identities_story_id", "character_identities", ["story_id"])

    op.create_table(
        "relationship_masks",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("story_id", sa.String(32), sa.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("character_id", sa.String(32), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("audience_character_id", sa.String(32), sa.ForeignKey("characters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("audience_label", sa.String(120), nullable=False, server_default=""),
        sa.Column("speech_style", sa.Text(), nullable=False, server_default=""),
        sa.Column("tells", sa.Text(), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_relationship_masks_story_id", "relationship_masks", ["story_id"])

    op.create_table(
        "character_states",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("story_id", sa.String(32), sa.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("character_id", sa.String(32), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_id", sa.String(32), sa.ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("label", sa.String(120), nullable=False, server_default=""),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("kind", sa.String(24), nullable=False, server_default="temporary"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_character_states_story_id", "character_states", ["story_id"])

    op.create_table(
        "place_identities",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("story_id", sa.String(32), sa.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("location_id", sa.String(32), sa.ForeignKey("locations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False, server_default=""),
        sa.Column("atmosphere", sa.Text(), nullable=False, server_default=""),
        sa.Column("sensory_palette", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("visual_anchors", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("spatial_layout", sa.Text(), nullable=False, server_default=""),
        sa.Column("controls_space", sa.String(255), nullable=False, server_default=""),
        sa.Column("social_rules", sa.Text(), nullable=False, server_default=""),
        sa.Column("normal_behavior", sa.Text(), nullable=False, server_default=""),
        sa.Column("variations", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("symbolic_motif", sa.String(255), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("story_id", "location_id", name="uq_place_identity_location"),
    )
    op.create_index("ix_place_identities_story_id", "place_identities", ["story_id"])

    op.create_table(
        "voice_exceptions",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("story_id", sa.String(32), sa.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_id", sa.String(32), sa.ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("character_id", sa.String(32), sa.ForeignKey("characters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("line_excerpt", sa.Text(), nullable=False, server_default=""),
        sa.Column("note_kind", sa.String(64), nullable=False, server_default=""),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("story_id", "fingerprint", name="uq_voice_exception"),
    )
    op.create_index("ix_voice_exceptions_story_id", "voice_exceptions", ["story_id"])
    op.create_index("ix_voice_exceptions_fingerprint", "voice_exceptions", ["fingerprint"])

    op.create_table(
        "identity_versions",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("story_id", sa.String(32), sa.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("character_id", sa.String(32), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("note", sa.String(255), nullable=False, server_default=""),
        sa.Column("chapter_id", sa.String(32), sa.ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("story_id", "character_id", "version_no", name="uq_identity_version"),
    )
    op.create_index("ix_identity_versions_story_id", "identity_versions", ["story_id"])
    op.create_index("ix_identity_versions_character_id", "identity_versions", ["character_id"])


def downgrade() -> None:
    op.drop_index("ix_identity_versions_character_id", table_name="identity_versions")
    op.drop_index("ix_identity_versions_story_id", table_name="identity_versions")
    op.drop_table("identity_versions")

    op.drop_index("ix_voice_exceptions_fingerprint", table_name="voice_exceptions")
    op.drop_index("ix_voice_exceptions_story_id", table_name="voice_exceptions")
    op.drop_table("voice_exceptions")

    op.drop_index("ix_place_identities_story_id", table_name="place_identities")
    op.drop_table("place_identities")

    op.drop_index("ix_character_states_story_id", table_name="character_states")
    op.drop_table("character_states")

    op.drop_index("ix_relationship_masks_story_id", table_name="relationship_masks")
    op.drop_table("relationship_masks")

    op.drop_index("ix_character_identities_story_id", table_name="character_identities")
    op.drop_table("character_identities")
