"""subscriptions & entitlement: user plan columns, llm_runs.key_source, subscriptions table

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-31
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── users: denormalized entitlement cache ────────────────────────────────
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("plan_tier", sa.String(32), nullable=False, server_default="free"))
        batch.add_column(sa.Column("plan_status", sa.String(32), nullable=False, server_default="none"))
        batch.add_column(sa.Column("is_admin", sa.Boolean, nullable=False, server_default=sa.text("false")))

    # ── llm_runs: which key paid for the call (the usage-meter unit) ──────────
    with op.batch_alter_table("llm_runs") as batch:
        batch.add_column(sa.Column("key_source", sa.String(16), nullable=False, server_default="none"))
    op.create_index("ix_llm_runs_key_source", "llm_runs", ["key_source"])

    # ── subscriptions: provider-agnostic billing record ──────────────────────
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("tier", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("external_customer_id", sa.String(255), nullable=False, server_default=""),
        sa.Column("external_subscription_id", sa.String(255), nullable=False, server_default=""),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("raw", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"])
    op.create_index("ix_subscriptions_external_subscription_id", "subscriptions", ["external_subscription_id"])


def downgrade() -> None:
    op.drop_index("ix_subscriptions_external_subscription_id", table_name="subscriptions")
    op.drop_index("ix_subscriptions_user_id", table_name="subscriptions")
    op.drop_table("subscriptions")

    op.drop_index("ix_llm_runs_key_source", table_name="llm_runs")
    with op.batch_alter_table("llm_runs") as batch:
        batch.drop_column("key_source")

    with op.batch_alter_table("users") as batch:
        batch.drop_column("is_admin")
        batch.drop_column("plan_status")
        batch.drop_column("plan_tier")
