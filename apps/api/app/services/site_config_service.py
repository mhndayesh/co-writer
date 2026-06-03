"""Owner-managed, site-wide config (the `site_settings` singleton row) loaded as
an immutable snapshot and cached in-process.

Why a snapshot + cache: the entitlement and provider-resolution layer
(`entitlement_service.get_entitlement`, `plans.plan_limit`, `factory`) is
synchronous and is called on the hot path of every AI request. Rather than make
all of it async to read the DB, an async caller fetches this snapshot once
(it has the `db`) and passes it down.

Cache: process-local with a short TTL, plus explicit `invalidate()` from the
PUT handler. The TTL self-heals staleness in a multi-process deployment where
one worker's `invalidate()` can't reach the others — the config changes rarely
and only the owner changes it, so a few seconds of lag is acceptable.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_secret
from app.db.models import SiteSettings

_TTL_SECONDS = 30.0


@dataclass(frozen=True)
class SiteConfig:
    """A read-only view of site_settings. Blank/None means "fall back to env"."""
    house_provider: str | None = None
    house_base_url: str = ""
    house_model: str = ""
    house_embed_model: str = ""
    house_api_key: str = ""  # decrypted on load
    dev_ai_max_actions: int | None = None
    dev_ai_max_tokens: int | None = None
    free_trial_max_actions: int | None = None
    free_trial_max_tokens: int | None = None


# Sentinel empty config = "nothing configured, pure env fallback".
_EMPTY = SiteConfig()

_cache: SiteConfig | None = None
_cached_at: float = 0.0


def _from_row(row: SiteSettings | None) -> SiteConfig:
    if row is None:
        return _EMPTY
    return SiteConfig(
        house_provider=(row.house_provider or None),
        house_base_url=row.house_base_url or "",
        house_model=row.house_model or "",
        house_embed_model=row.house_embed_model or "",
        house_api_key=decrypt_secret(row.house_api_key_ciphertext or ""),
        dev_ai_max_actions=row.dev_ai_max_actions,
        dev_ai_max_tokens=row.dev_ai_max_tokens,
        free_trial_max_actions=row.free_trial_max_actions,
        free_trial_max_tokens=row.free_trial_max_tokens,
    )


async def get_site_config(db: AsyncSession) -> SiteConfig:
    """Return the cached site config, reloading from the DB when the TTL lapses."""
    global _cache, _cached_at
    now = time.monotonic()
    if _cache is None or (now - _cached_at) > _TTL_SECONDS:
        row = await db.get(SiteSettings, "singleton")
        _cache = _from_row(row)
        _cached_at = now
    return _cache


def invalidate() -> None:
    """Drop the cache so the next read reflects a just-saved change."""
    global _cache, _cached_at
    _cache = None
    _cached_at = 0.0
