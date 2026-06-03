"""Webhook idempotency ledger: billing_events table.

(provider, external_event_id) is unique so inbound provider webhooks are applied
exactly once despite at-least-once delivery + retries.

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-31
"""
import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "billing_events",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_event_id", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("provider", "external_event_id", name="uq_billing_event"),
    )


def downgrade() -> None:
    op.drop_table("billing_events")
