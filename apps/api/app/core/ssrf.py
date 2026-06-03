"""SSRF protection for user-supplied provider base_url values.

BYOK users configure base_url which the server fetches server-side. Without
validation this is a full-read SSRF oracle to cloud metadata, internal services
(postgres, neo4j, redis), and RFC-1918 networks. Every base_url must pass this
check on write AND on each request.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse

from app.core.errors import BadRequest

# Hostnames that are cloud metadata endpoints regardless of IP resolution.
_BLOCKED_HOSTNAMES: frozenset[str] = frozenset({
    "169.254.169.254",        # AWS/Azure/GCP IMDSv1
    "metadata.google.internal",
    "metadata.goog",
    "instance-data",
    "metadata",
})

# Known provider base-url prefixes — allow-listed so the check is stricter by default.
# Operators can extend this via ALLOWED_LLM_HOSTS env if needed.
_KNOWN_HOSTS: frozenset[str] = frozenset({
    "api.openai.com",
    "openrouter.ai",
    "api.anthropic.com",
    "generativelanguage.googleapis.com",
    "api.mistral.ai",
    "api.together.xyz",
    "api.groq.com",
})

# Regex for LM Studio / local-only deployments (only valid in development).
_LOCALHOST_RE = re.compile(r"^(localhost|127\.0\.0\.1|0\.0\.0\.0|\[?::1\]?)$", re.IGNORECASE)


def _is_private(ip_str: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
        return (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_multicast
            or addr.is_unspecified
            or addr.is_reserved
        )
    except ValueError:
        return True  # unparseable → treat as unsafe


def validate_provider_base_url(url: str) -> str:
    """Validate a user-supplied LLM provider base_url.

    Raises BadRequest with a safe message on any violation. Returns the
    (normalized) url on success so callers can use it directly.

    Checks:
    - Must be http:// or https://
    - Host must not be a cloud metadata endpoint
    - Host must not resolve to a loopback / private / reserved IP
    - Must have a non-empty host

    Note: we do NOT enforce an allowlist — users may self-host OpenAI-compat
    proxies on public IPs. We only block SSRF-reachable private/metadata space.
    """
    if not url:
        return url  # empty = use the preset default; no external call made

    url = url.strip().rstrip("/")

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise BadRequest(
            "Provider base URL must start with http:// or https://."
        )

    host = parsed.hostname or ""
    if not host:
        raise BadRequest("Provider base URL is missing a hostname.")

    # Block known metadata hostnames directly (before DNS resolution).
    if host.lower() in _BLOCKED_HOSTNAMES:
        raise BadRequest("That hostname is not allowed as a provider URL.")

    # Block localhost / loopback by name.
    if _LOCALHOST_RE.match(host):
        raise BadRequest(
            "localhost / loopback addresses are not allowed as provider URLs."
        )

    # Resolve the host and reject private/reserved IPs. NOTE: this alone does NOT
    # stop DNS-rebinding — httpx re-resolves the hostname at connect time, so a
    # low-TTL domain can flip to an internal IP *after* this check. Callers that
    # fetch a user-supplied URL must ALSO re-validate at request time, which the
    # OpenAI-compatible provider does via assert_base_url_safe() before every call.
    try:
        resolved = socket.getaddrinfo(host, None, socket.AF_UNSPEC)
    except OSError:
        # Unresolvable host — safer to reject than allow; mis-config is surfaced
        # at configuration time rather than silently failing on the first call.
        raise BadRequest(
            f"Provider host '{host}' could not be resolved. "
            "Check the URL and try again."
        )

    for *_, sockaddr in resolved:
        ip = sockaddr[0]
        if _is_private(ip):
            raise BadRequest(
                f"Provider host '{host}' resolves to a private/internal IP address "
                "and cannot be used as an LLM provider URL."
            )

    # Opt-in strict allowlist (ALLOWED_LLM_HOSTS). When configured, the host must be
    # a built-in known provider OR an operator-listed host — a hard SSRF lockdown.
    # When unset, no allowlist is enforced (self-hosted proxies stay allowed).
    from app.core.config import get_settings

    extra = get_settings().allowed_llm_hosts_list
    if extra:
        allowed = _KNOWN_HOSTS | set(extra)
        if host.lower() not in allowed:
            raise BadRequest(
                f"Provider host '{host}' is not in the allowed providers list "
                "(ALLOWED_LLM_HOSTS). Ask the site operator to add it."
            )

    return url


def assert_base_url_safe(url: str) -> None:
    """Request-time re-validation to shrink the DNS-rebinding TOCTOU window.

    The write-time check (validate_provider_base_url) can be defeated by a
    low-TTL domain that returns a public IP at validation and an internal IP at
    connect. Re-running the resolve+private-IP check immediately before each
    outbound request means an attacker must win a sub-millisecond race between
    this lookup and httpx's own connect-time lookup (which a caching stub
    resolver usually defeats). Raises BadRequest if the host now resolves into
    private/metadata space. Only call this for USER-supplied URLs — trusted
    preset localhost URLs (LM Studio) would be wrongly rejected."""
    validate_provider_base_url(url)
