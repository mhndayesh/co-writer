"""Fix publication_chapters unique constraint: replace full UniqueConstraint with
a partial index so only one is_latest=TRUE row per (publication_id, chapter_number)
is enforced — multiple historical (is_latest=FALSE) rows are now allowed.

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-31
"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    is_pg = conn.dialect.name == "postgresql"

    if is_pg:
        # Drop the old plain UniqueConstraint and replace with a partial index.
        op.drop_constraint("uq_pub_chapter_latest", "publication_chapters", type_="unique")
        op.execute("""
            CREATE UNIQUE INDEX uq_pub_chapter_latest
            ON publication_chapters (publication_id, chapter_number)
            WHERE is_latest = TRUE
        """)
    else:
        # SQLite: batch mode can't drop constraints by name; recreate the table.
        with op.batch_alter_table("publication_chapters", recreate="always") as batch:
            # Drop the old constraint (batch recreate rebuilds without it).
            batch.drop_constraint("uq_pub_chapter_latest", type_="unique")
        # Create the partial index after the table is rebuilt.
        op.execute("""
            CREATE UNIQUE INDEX uq_pub_chapter_latest
            ON publication_chapters (publication_id, chapter_number)
            WHERE is_latest = 1
        """)


def downgrade() -> None:
    conn = op.get_bind()
    is_pg = conn.dialect.name == "postgresql"

    op.drop_index("uq_pub_chapter_latest", table_name="publication_chapters")

    if is_pg:
        op.create_unique_constraint(
            "uq_pub_chapter_latest",
            "publication_chapters",
            ["publication_id", "chapter_number", "is_latest"],
        )
    else:
        with op.batch_alter_table("publication_chapters") as batch:
            batch.create_unique_constraint(
                "uq_pub_chapter_latest",
                ["publication_id", "chapter_number", "is_latest"],
            )
