from __future__ import annotations


def redis_settings():
    """ARQ RedisSettings derived from the app's REDIS_URL config.

    Both the worker and the async-export submit endpoints must agree on WHERE
    Redis is. `RedisSettings()` with no args hard-defaults to localhost:6379,
    which silently breaks in the standard compose topology (Redis is a separate
    `redis` host) — the worker connects nowhere and export submit returns "queue
    unavailable". Honour REDIS_URL when set; fall back to the localhost default
    only for bare local dev.
    """
    from arq.connections import RedisSettings

    from app.core.config import get_settings

    url = get_settings().redis_url
    return RedisSettings.from_dsn(url) if url else RedisSettings()
