"""Graph self-heal + client idempotency

Two additive changes (no data migration, no locks of consequence):

1. `stories.graph_synced_at` — timestamp of the last successful Neo4j projection.
   NULL = never synced. A background reconciler retries any story whose
   graph_status != "ok", so a Neo4j outage during Flow approve self-heals.

2. `idempotency_keys` — dedupe ledger for client mutations that aren't naturally
   idempotent (Flow approve, publish push). Unique on (user_id, scope, idem_key);
   the stored response is replayed verbatim on a retried request.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "stories",
        sa.Column("graph_synced_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(32),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scope", sa.String(120), nullable=False),
        sa.Column("idem_key", sa.String(128), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "scope", "idem_key", name="uq_idempotency_key"),
    )
    op.create_index("ix_idempotency_keys_user_id", "idempotency_keys", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_idempotency_keys_user_id", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")
    op.drop_column("stories", "graph_synced_at")
