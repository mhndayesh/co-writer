"""Cover images + in-app notifications

Additive:
1. stories.cover_image_url / chapters.cover_image_url — optional cover art
   (uploaded path or http(s) URL). publications.cover_image_url already existed.
2. notifications — in-app reader notifications (e.g. a followed story posted a new
   chapter). Email delivery is a later add-on.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stories", sa.Column("cover_image_url", sa.Text(), nullable=True))
    op.add_column("chapters", sa.Column("cover_image_url", sa.Text(), nullable=True))

    op.create_table(
        "notifications",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("user_id", sa.String(length=32),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False, server_default="new_chapter"),
        sa.Column("publication_id", sa.String(length=32),
                  sa.ForeignKey("publications.id", ondelete="CASCADE"), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("link", sa.Text(), nullable=True),
        sa.Column("read", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_publication_id", "notifications", ["publication_id"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])
    op.create_index("ix_notifications_user_read", "notifications", ["user_id", "read"])


def downgrade() -> None:
    op.drop_index("ix_notifications_user_read", table_name="notifications")
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ix_notifications_publication_id", table_name="notifications")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_table("notifications")
    op.drop_column("chapters", "cover_image_url")
    op.drop_column("stories", "cover_image_url")
