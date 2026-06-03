"""Guard against models ⇄ migrations drift.

Production builds its schema with Alembic, but the test suite builds it from the
ORM via `Base.metadata.create_all` — so a table/column that exists in models but
is missing from a migration (or vice-versa) would otherwise pass CI silently
(this is exactly how the 0005 publication-chapter constraint shipped wrong until
0007). This test upgrades a fresh DB through EVERY migration and asserts there is
no table- or column-level difference vs the ORM metadata.

Index/server_default/nullable nuances are intentionally NOT asserted — they're
cosmetic and noisy to reflect across dialects. The high-value signal is "a model
table/column has no migration", which this catches.
"""
import pathlib

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine

from app.core.config import get_settings
from app.db.base import Base
import app.db.models  # noqa: F401 — registers core + publishing models on Base.metadata

API_DIR = pathlib.Path(__file__).resolve().parents[1]

_STRUCTURAL = {"add_table", "remove_table", "add_column", "remove_column"}


def _structural_diffs(diffs) -> list[str]:
    out: list[str] = []
    for d in diffs:
        # compare_metadata yields tuples (column ops) and lists-of-tuples (table ops).
        for it in (d if isinstance(d, list) else [d]):
            if isinstance(it, tuple) and it and it[0] in _STRUCTURAL:
                # it is like ('add_column', schema, table, Column) or ('add_table', Table)
                out.append(" ".join(str(x) for x in it[:3]))
    return out


def test_models_match_migrations(tmp_path):
    db_file = tmp_path / "drift.db"

    # env.py reads the URL from settings; point it at a throwaway SQLite file and
    # run every migration. (Migrations are dialect-aware and run on SQLite here.)
    settings = get_settings()
    prev_url = settings.database_url
    settings.database_url = f"sqlite+aiosqlite:///{db_file}"
    try:
        cfg = Config(str(API_DIR / "alembic.ini"))
        cfg.set_main_option("script_location", str(API_DIR / "migrations"))
        command.upgrade(cfg, "head")  # also asserts every migration APPLIES cleanly
    finally:
        settings.database_url = prev_url

    engine = create_engine(f"sqlite:///{db_file}")
    try:
        with engine.connect() as conn:
            ctx = MigrationContext.configure(
                conn, opts={"target_metadata": Base.metadata, "render_as_batch": True}
            )
            diffs = compare_metadata(ctx, Base.metadata)
    finally:
        engine.dispose()

    problems = _structural_diffs(diffs)
    assert not problems, (
        "models vs migrations drift — these tables/columns exist in one but not the "
        "other (add a migration, or fix the model):\n  " + "\n  ".join(problems)
    )
