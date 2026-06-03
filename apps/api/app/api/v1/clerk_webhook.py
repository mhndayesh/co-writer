"""Clerk → backend webhook.

Clerk delivers user.created/updated/deleted events here (signed with Svix) so the
local users table stays in sync with identity changes made in Clerk's UI. We
verify the Svix signature by hand (HMAC-SHA256 over `id.timestamp.body`) to avoid
pulling in the svix dependency.

Configure in the Clerk Dashboard → Webhooks: endpoint URL
`<api>/v1/webhooks/clerk`, subscribe to the `user.*` events, then copy the
signing secret (whsec_...) into CLERK_WEBHOOK_SECRET.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time

from fastapi import APIRouter, Header, Request

from app.core.config import get_settings
from app.core.deps import DB
from app.core.errors import Unauthorized, envelope_ok
from app.services import clerk_service

log = logging.getLogger("gink.clerk")

router = APIRouter()


def _verify_svix(secret: str, svix_id: str, svix_timestamp: str, svix_signature: str, body: bytes) -> bool:
    """Verify a Svix webhook signature. `svix_signature` is a space-separated list
    of `v1,<base64sig>` entries; a match on any one passes."""
    if not (secret and svix_id and svix_timestamp and svix_signature):
        return False
    # Secret is "whsec_<base64>"; the signing key is the decoded base64 part.
    key = base64.b64decode(secret.split("_", 1)[1]) if secret.startswith("whsec_") else secret.encode()
    signed_content = f"{svix_id}.{svix_timestamp}.{body.decode()}".encode()
    expected = base64.b64encode(hmac.new(key, signed_content, hashlib.sha256).digest()).decode()
    for part in svix_signature.split():
        _, _, sig = part.partition(",")
        if sig and hmac.compare_digest(sig, expected):
            return True
    return False


@router.post("/clerk")
async def clerk_webhook(
    request: Request,
    db: DB,
    svix_id: str | None = Header(default=None, alias="svix-id"),
    svix_timestamp: str | None = Header(default=None, alias="svix-timestamp"),
    svix_signature: str | None = Header(default=None, alias="svix-signature"),
):
    s = get_settings()
    if not s.clerk_webhook_secret:
        # Refuse rather than silently accept unsigned events.
        raise Unauthorized("Clerk webhook secret not configured")

    # Replay protection: reject stale/forward-dated deliveries. Svix sends the
    # timestamp as unix seconds; the HMAC binds it, so a captured request can't be
    # replayed beyond this window (and can't be re-timestamped without the secret).
    try:
        skew = abs(time.time() - int((svix_timestamp or "").strip()))
    except (TypeError, ValueError):
        raise Unauthorized("Invalid webhook timestamp")
    if skew > 300:  # 5 minutes
        raise Unauthorized("Webhook timestamp outside the allowed window")

    body = await request.body()
    if not _verify_svix(s.clerk_webhook_secret, svix_id or "", svix_timestamp or "", svix_signature or "", body):
        raise Unauthorized("Invalid webhook signature")

    event = json.loads(body)
    event_type = event.get("type", "")
    data = event.get("data", {}) or {}
    if event_type.startswith("user."):
        await clerk_service.upsert_from_webhook(event_type, data, db)
    else:
        log.info("Ignoring Clerk webhook event %s", event_type)
    return envelope_ok({"received": True})
