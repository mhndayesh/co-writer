"""Add reader_profiles.profile_public so a writer can hide their public profile.

Previously the public profile endpoint hardcoded profile_public=True and ignored
the user's choice; this persists the flag (default public for existing rows).

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-31
"""
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    default = sa.text("true") if conn.dialect.name == "postgresql" else sa.text("1")
    op.add_column(
        "reader_profiles",
        sa.Column(
            "profile_public",
            sa.Boolean(),
            nullable=False,
            server_default=default,
        ),
    )


def downgrade() -> None:
    op.drop_column("reader_profiles", "profile_public")
