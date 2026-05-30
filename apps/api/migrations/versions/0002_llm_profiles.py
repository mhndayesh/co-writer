"""split LLM routing: mode column + llm_profiles table

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-30
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Additive: existing rows default to mode="single" → no behavior change.
    with op.batch_alter_table("user_llm_settings") as batch:
        batch.add_column(sa.Column("mode", sa.String(16), nullable=False, server_default="single"))

    op.create_table(
        "llm_profiles",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False, server_default="lmstudio"),
        sa.Column("base_url", sa.String(500), nullable=False, server_default=""),
        sa.Column("model", sa.String(200), nullable=False, server_default=""),
        sa.Column("embed_model", sa.String(200), nullable=False, server_default=""),
        sa.Column("api_key_ciphertext", sa.Text, nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "role", name="uq_llm_profile_user_role"),
    )
    op.create_index("ix_llm_profiles_user_id", "llm_profiles", ["user_id"])


def downgrade() -> None:
    op.drop_table("llm_profiles")
    with op.batch_alter_table("user_llm_settings") as batch:
        batch.drop_column("mode")
