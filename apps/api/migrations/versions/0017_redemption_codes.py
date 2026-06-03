"""Redemption (promo/gift) codes + hard plan expiry

Additive:
1. users.plan_expires_at — hard expiry for a non-auto-renewing grant (promo/manual);
   NULL = no expiry. entitlement_service lapses a paid tier to free once it passes.
2. redemption_codes — owner-minted codes (tier + duration + max uses).
3. code_redemptions — one row per (code, user); enforces one redemption per user.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("plan_expires_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "redemption_codes",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("tier", sa.String(length=32), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=True),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column("uses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("note", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=32), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_redemption_codes_code", "redemption_codes", ["code"], unique=True)

    op.create_table(
        "code_redemptions",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("code_id", sa.String(length=32), sa.ForeignKey("redemption_codes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tier", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("code_id", "user_id", name="uq_code_redemption_per_user"),
    )
    op.create_index("ix_code_redemptions_code_id", "code_redemptions", ["code_id"])
    op.create_index("ix_code_redemptions_user_id", "code_redemptions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_code_redemptions_user_id", table_name="code_redemptions")
    op.drop_index("ix_code_redemptions_code_id", table_name="code_redemptions")
    op.drop_table("code_redemptions")
    op.drop_index("ix_redemption_codes_code", table_name="redemption_codes")
    op.drop_table("redemption_codes")
    op.drop_column("users", "plan_expires_at")
