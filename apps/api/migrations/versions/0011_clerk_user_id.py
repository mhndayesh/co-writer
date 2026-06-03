"""Clerk auth: add users.clerk_user_id and relax password_hash

Adds the nullable, unique `clerk_user_id` column that links a local user row to
its Clerk account (user_xxx). Also makes `password_hash` nullable, since users
provisioned through Clerk have no local password. The users table is retained as
the source of truth for app data (stories, billing, profile) — Clerk only owns
identity/credentials.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("clerk_user_id", sa.String(64), nullable=True))
    op.create_index("ix_users_clerk_user_id", "users", ["clerk_user_id"], unique=True)
    with op.batch_alter_table("users") as batch:
        batch.alter_column("password_hash", existing_type=sa.String(255), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.alter_column("password_hash", existing_type=sa.String(255), nullable=False)
    op.drop_index("ix_users_clerk_user_id", table_name="users")
    op.drop_column("users", "clerk_user_id")
