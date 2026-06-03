"""publishing platform

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-31
"""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    is_pg = conn.dialect.name == "postgresql"

    # PostgreSQL-only: create ENUM types (safe idempotent via DO block)
    if is_pg:
        op.execute("""
            DO $$ BEGIN
                CREATE TYPE publication_status AS ENUM ('draft','published','unlisted','archived');
            EXCEPTION WHEN duplicate_object THEN null; END $$;
        """)
        op.execute("""
            DO $$ BEGIN
                CREATE TYPE release_type AS ENUM ('complete','serial');
            EXCEPTION WHEN duplicate_object THEN null; END $$;
        """)
        op.execute("""
            DO $$ BEGIN
                CREATE TYPE review_status AS ENUM ('pending','approved','declined','flagged');
            EXCEPTION WHEN duplicate_object THEN null; END $$;
        """)
        op.execute("""
            DO $$ BEGIN
                CREATE TYPE notification_pref AS ENUM ('immediate','digest','none');
            EXCEPTION WHEN duplicate_object THEN null; END $$;
        """)

    # publications
    op.create_table(
        "publications",
        sa.Column("id",       sa.String(32), primary_key=True),
        sa.Column("story_id", sa.String(32), sa.ForeignKey("stories.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("user_id",  sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("slug",             sa.String(200), nullable=False, unique=True),
        sa.Column("status",           sa.String(20),  nullable=False, server_default="draft"),
        sa.Column("release_type",     sa.String(20),  nullable=False, server_default="complete"),
        sa.Column("cover_image_url",  sa.Text,        nullable=True),
        sa.Column("tagline",          sa.String(300), nullable=True),
        sa.Column("content_warnings", sa.JSON,        nullable=False, server_default="[]"),
        sa.Column("genre",            sa.String(60),  nullable=True),
        sa.Column("tags",             sa.JSON,        nullable=False, server_default="[]"),
        sa.Column("published_at",           sa.DateTime, nullable=True),
        sa.Column("last_chapter_pushed_at", sa.DateTime, nullable=True),
        sa.Column("total_planned_chapters", sa.Integer,  nullable=True),
        sa.Column("view_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime, nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_publications_slug",    "publications", ["slug"])
    op.create_index("ix_publications_user_id", "publications", ["user_id"])
    op.create_index("ix_publications_status",  "publications", ["status"])
    op.create_index("ix_publications_genre",   "publications", ["genre"])

    # publication_chapters
    op.create_table(
        "publication_chapters",
        sa.Column("id",             sa.String(32), primary_key=True),
        sa.Column("publication_id", sa.String(32),
                  sa.ForeignKey("publications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_number", sa.Integer,     nullable=False),
        sa.Column("version",        sa.Integer,     nullable=False, server_default="1"),
        sa.Column("title",          sa.String(300), nullable=False),
        sa.Column("content",        sa.Text,        nullable=False),
        sa.Column("word_count",     sa.Integer,     nullable=False, server_default="0"),
        sa.Column("pushed_at",      sa.DateTime,    nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("is_latest",      sa.Boolean,     nullable=False, server_default="1"),
        sa.UniqueConstraint("publication_id", "chapter_number", "is_latest",
                            name="uq_pub_chapter_latest"),
    )
    op.create_index("ix_pub_chapters_pub_id", "publication_chapters", ["publication_id"])
    op.create_index("ix_pub_chapters_latest", "publication_chapters",
                    ["publication_id", "chapter_number", "is_latest"])

    # reader_profiles
    op.create_table(
        "reader_profiles",
        sa.Column("user_id",      sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("display_name", sa.String(80),  nullable=True),
        sa.Column("bio",          sa.String(500), nullable=True),
        sa.Column("avatar_url",   sa.Text,        nullable=True),
        sa.Column("is_age_verified", sa.Boolean,  nullable=False, server_default="0"),
        sa.Column("created_at",   sa.DateTime,    nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    # reading_progress
    op.create_table(
        "reading_progress",
        sa.Column("id",             sa.String(32), primary_key=True),
        sa.Column("reader_id",      sa.String(32),
                  sa.ForeignKey("users.id",        ondelete="CASCADE"), nullable=False),
        sa.Column("publication_id", sa.String(32),
                  sa.ForeignKey("publications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("last_chapter_number",   sa.Integer, nullable=False, server_default="0"),
        sa.Column("completion_percentage", sa.Float,   nullable=False, server_default="0"),
        sa.Column("started_at",   sa.DateTime, nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("last_read_at", sa.DateTime, nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("is_following", sa.Boolean,  nullable=False, server_default="0"),
        sa.UniqueConstraint("reader_id", "publication_id", name="uq_reading_progress"),
    )
    op.create_index("ix_reading_progress_reader", "reading_progress", ["reader_id"])
    op.create_index("ix_reading_progress_pub",    "reading_progress", ["publication_id"])

    # story_ratings
    op.create_table(
        "story_ratings",
        sa.Column("id",             sa.String(32), primary_key=True),
        sa.Column("reader_id",      sa.String(32),
                  sa.ForeignKey("users.id",        ondelete="CASCADE"), nullable=False),
        sa.Column("publication_id", sa.String(32),
                  sa.ForeignKey("publications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("overall",          sa.SmallInteger, nullable=False),
        sa.Column("score_story",      sa.SmallInteger, nullable=True),
        sa.Column("score_craft",      sa.SmallInteger, nullable=True),
        sa.Column("score_characters", sa.SmallInteger, nullable=True),
        sa.Column("score_pacing",     sa.SmallInteger, nullable=True),
        sa.Column("score_world",      sa.SmallInteger, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime, nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("reader_id", "publication_id", name="uq_story_rating"),
    )
    op.create_index("ix_story_ratings_pub", "story_ratings", ["publication_id"])

    # reviews
    op.create_table(
        "reviews",
        sa.Column("id",             sa.String(32), primary_key=True),
        sa.Column("reader_id",      sa.String(32),
                  sa.ForeignKey("users.id",        ondelete="CASCADE"), nullable=False),
        sa.Column("publication_id", sa.String(32),
                  sa.ForeignKey("publications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("body",           sa.Text,        nullable=False),
        sa.Column("status",         sa.String(20),  nullable=False, server_default="pending"),
        sa.Column("flagged_reason", sa.String(200), nullable=True),
        sa.Column("approved_at",    sa.DateTime,    nullable=True),
        sa.Column("created_at",     sa.DateTime,    nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("reader_id", "publication_id", name="uq_review"),
    )
    op.create_index("ix_reviews_pub_status", "reviews", ["publication_id", "status"])

    # private_notes
    op.create_table(
        "private_notes",
        sa.Column("id",             sa.String(32), primary_key=True),
        sa.Column("reader_id",      sa.String(32),
                  sa.ForeignKey("users.id",        ondelete="CASCADE"), nullable=False),
        sa.Column("publication_id", sa.String(32),
                  sa.ForeignKey("publications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_number",    sa.Integer,     nullable=True),
        sa.Column("passage_reference", sa.String(500), nullable=True),
        sa.Column("body",              sa.Text,        nullable=False),
        sa.Column("writer_reply",      sa.Text,        nullable=True),
        sa.Column("replied_at",        sa.DateTime,    nullable=True),
        sa.Column("is_read_by_writer", sa.Boolean,     nullable=False, server_default="0"),
        sa.Column("created_at",        sa.DateTime,    nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_private_notes_pub",    "private_notes", ["publication_id"])
    op.create_index("ix_private_notes_reader", "private_notes", ["reader_id"])

    # publication_follows
    op.create_table(
        "publication_follows",
        sa.Column("reader_id",      sa.String(32),
                  sa.ForeignKey("users.id",        ondelete="CASCADE"), primary_key=True),
        sa.Column("publication_id", sa.String(32),
                  sa.ForeignKey("publications.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("followed_at",       sa.DateTime, nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("notification_pref", sa.String(20), nullable=False, server_default="immediate"),
    )
    op.create_index("ix_pub_follows_pub", "publication_follows", ["publication_id"])


def downgrade() -> None:
    op.drop_table("publication_follows")
    op.drop_table("private_notes")
    op.drop_table("reviews")
    op.drop_table("story_ratings")
    op.drop_table("reading_progress")
    op.drop_table("reader_profiles")
    op.drop_table("publication_chapters")
    op.drop_table("publications")

    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS notification_pref")
        op.execute("DROP TYPE IF EXISTS review_status")
        op.execute("DROP TYPE IF EXISTS release_type")
        op.execute("DROP TYPE IF EXISTS publication_status")
