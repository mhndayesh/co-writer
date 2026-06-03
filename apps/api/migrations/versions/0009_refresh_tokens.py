"""Refresh-token rotation/revocation: add refresh_tokens table + users.token_version.

Lets refresh tokens be rotated and revoked (a stateless JWT can't be), with
refresh-token-reuse detection, plus a session epoch (token_version) so logout /
password change invalidates outstanding access tokens.

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-31
"""
import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    is_pg = conn.dialect.name == "postgresql"
    false_default = sa.text("false") if is_pg else sa.text("0")

    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("jti", sa.String(length=32), primary_key=True),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=false_default),
        sa.Column("replaced_by", sa.String(length=32), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_column("users", "token_version")
