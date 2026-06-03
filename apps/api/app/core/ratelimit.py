"""Shared SlowAPI limiter.

Lives in its own module so route modules can import the same `limiter` instance
for per-route `@limiter.limit(...)` decorators.

## Proxy-IP correctness
Behind Caddy (or any reverse proxy), `request.client.host` is the PROXY's IP,
not the real client — every user would share one rate-limit bucket. We use a
custom `key_func` that reads `X-Forwarded-For` (set by Caddy) to get the real
client IP. The uvicorn `--proxy-headers --forwarded-allow-ips='*'` flags (set in
the Dockerfile CMD) instruct uvicorn to populate `request.client` from
`X-Forwarded-For`, but `get_remote_address` would still read the possibly-already-
corrected socket peer. Using our own key_func ensures consistency regardless of
uvicorn's proxy-header mode.

## Storage
Uses Redis for a shared bucket across worker processes when REDIS_URL is set.
Falls back to per-process in-memory (multiply limits by worker count mentally).
`swallow_errors=True` so a Redis hiccup degrades to "no limit" rather than 500.

## Enabled flag
Disabled in `development` (and the test suite, which defaults to development) so
tests don't self-throttle from a single IP.
"""
from __future__ import annotations

from starlette.requests import Request

from slowapi import Limiter

from app.core.config import get_settings

_s = get_settings()


def _real_client_ip(request: Request) -> str:
    """Read the real client IP from X-Forwarded-For (set by Caddy/any LB).

    Uses the RIGHTMOST entry — the IP appended by our own trusted reverse proxy
    (Caddy) for the connection it accepted. The leftmost entries are
    client-supplied and trivially spoofable, so keying the limiter on them lets
    an attacker prepend a random IP per request and get a fresh bucket every
    time, bypassing the limit. (Assumes a single trusted proxy hop in front of
    the app; bump the index if you add more trusted proxies.)

    Falls back to request.client.host if the header is absent (direct/local).
    """
    xff = request.headers.get("X-Forwarded-For") or request.headers.get("x-forwarded-for")
    if xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if parts:
            return parts[-1]
    return request.client.host if request.client else "unknown"


limiter = Limiter(
    key_func=_real_client_ip,
    default_limits=["200/minute"],
    storage_uri=_s.redis_url or None,
    enabled=_s.is_development is False,
    swallow_errors=True,
)
