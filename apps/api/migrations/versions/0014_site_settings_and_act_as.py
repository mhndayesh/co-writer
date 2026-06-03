"""Owner control panel + shape-shift

Additive only:
1. site_settings  — single-row, owner-managed house default AI + tunable usage caps
2. users.act_as_tier — owner-only "view as" tier for testing the real per-tier experience

Both are nullable/blank-defaulted, so an existing deploy behaves exactly as before
until the owner configures them.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "site_settings",
        sa.Column("id", sa.String(16), primary_key=True),
        sa.Column("house_provider", sa.String(32), nullable=True),
        sa.Column("house_base_url", sa.String(512), nullable=False, server_default=""),
        sa.Column("house_model", sa.String(200), nullable=False, server_default=""),
        sa.Column("house_embed_model", sa.String(200), nullable=False, server_default=""),
        sa.Column("house_api_key_ciphertext", sa.Text(), nullable=False, server_default=""),
        sa.Column("dev_ai_max_actions", sa.Integer(), nullable=True),
        sa.Column("dev_ai_max_tokens", sa.Integer(), nullable=True),
        sa.Column("free_trial_max_actions", sa.Integer(), nullable=True),
        sa.Column("free_trial_max_tokens", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("act_as_tier", sa.String(16), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("act_as_tier")
    op.drop_table("site_settings")
