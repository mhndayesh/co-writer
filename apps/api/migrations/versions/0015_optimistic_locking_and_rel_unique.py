"""Optimistic-concurrency tokens + character-relationship uniqueness

Additive, safe to run on a populated DB:
1. version_id on characters / chapters / scene_cards — SQLAlchemy version_id_col;
   added NOT NULL DEFAULT 1 so existing rows backfill to 1.
2. Unique (story_id, source_id, target_id) on character_relationships — the
   documented "one row per pair" invariant. Pre-existing duplicates (only the
   manual POST route could create them) are collapsed to one row first.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("characters", "chapters", "scene_cards"):
        op.add_column(
            table,
            sa.Column("version_id", sa.Integer(), nullable=False, server_default="1"),
        )

    # Collapse any duplicate (story_id, source_id, target_id) edges to one row,
    # keeping the lexicographically-smallest id, BEFORE enforcing uniqueness.
    # (SQLite + Postgres both allow deleting against a subquery on the same table.)
    op.execute(
        """
        DELETE FROM character_relationships
        WHERE id NOT IN (
            SELECT MIN(id) FROM character_relationships
            GROUP BY story_id, source_id, target_id
        )
        """
    )

    # batch_alter_table so SQLite (which can't ALTER ADD CONSTRAINT) recreates the
    # table; on Postgres this is a plain ADD CONSTRAINT.
    with op.batch_alter_table("character_relationships") as batch:
        batch.create_unique_constraint(
            "uq_character_relationship_pair", ["story_id", "source_id", "target_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("character_relationships") as batch:
        batch.drop_constraint("uq_character_relationship_pair", type_="unique")
    for table in ("scene_cards", "chapters", "characters"):
        op.drop_column(table, "version_id")
