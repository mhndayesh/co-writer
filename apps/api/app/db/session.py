from collections.abc import AsyncIterator
from typing import Optional

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

_settings = get_settings()


def _normalize_db_url(url: str) -> str:
    """Force the asyncpg driver on bare Postgres URLs. Managed hosts (Railway,
    Render, Heroku, Supabase) hand out `postgresql://` (or legacy `postgres://`),
    but our async engine needs `postgresql+asyncpg://`. Normalizing here means the
    operator can paste the provider's URL verbatim and it just works."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    return url


DATABASE_URL = _normalize_db_url(_settings.database_url)

connect_args: dict = {}
pool_kwargs: dict = {}

if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
else:
    # PostgreSQL connection pool tuning
    pool_kwargs = {
        "pool_size": 10,
        "max_overflow": 20,
        "pool_pre_ping": True,
        "pool_recycle": 3600,
    }

engine = create_async_engine(
    DATABASE_URL,
    future=True,
    echo=False,
    connect_args=connect_args,
    **pool_kwargs,
)

if DATABASE_URL.startswith("sqlite"):
    # SQLite ships with foreign-key enforcement OFF per-connection, so every
    # `ON DELETE CASCADE` / `SET NULL` in the schema is a silent no-op — deleting a
    # story would orphan ~20 child tables. Prod is Postgres (FKs always on), but the
    # whole test suite runs on SQLite, so without this a cascade regression sails
    # through CI. Turn it on for every pooled connection.
    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_enable_foreign_keys(dbapi_conn, _record):  # pragma: no cover - trivial
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


# ---------------------------------------------------------------------------
# Optional Redis client (used for caching and ARQ queue)
# ---------------------------------------------------------------------------

_redis: Optional[object] = None


def get_redis():
    """Return an async Redis client if REDIS_URL is configured, else None."""
    global _redis
    if _redis is None and _settings.redis_url:
        try:
            import redis.asyncio as aioredis
            _redis = aioredis.from_url(_settings.redis_url, decode_responses=False)
        except ImportError:
            pass
    return _redis
