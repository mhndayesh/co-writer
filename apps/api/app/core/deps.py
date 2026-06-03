import logging
from typing import Annotated

import jwt
from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import NotFound, Unauthorized
from app.core.security import decode_token, verify_clerk_token
from app.db.models import Story, User
from app.db.session import get_db
from app.services import clerk_service

log = logging.getLogger("gink.auth")


async def _user_from_clerk_token(token: str, db: AsyncSession) -> User:
    """Verify a Clerk RS256 session token and resolve it to a local user."""
    try:
        claims = verify_clerk_token(token)
    except Exception:
        log.warning("Clerk token verification failed", exc_info=True)
        raise Unauthorized("Invalid or expired token") from None
    try:
        return await clerk_service.resolve_user(claims, db)
    except Unauthorized:
        raise
    except Exception:
        log.warning("Clerk user resolution failed", exc_info=True)
        raise Unauthorized("Could not resolve account") from None


async def _user_from_legacy_token(token: str, db: AsyncSession) -> User:
    """Validate a legacy HS256 access token (tests / pre-Clerk sessions)."""
    try:
        payload = decode_token(token)
    except Exception:
        # Generic message to the client; the specific PyJWT reason (expired vs
        # malformed vs bad signature) is an info leak, so keep it server-side.
        log.warning("access token decode failed", exc_info=True)
        raise Unauthorized("Invalid or expired token") from None
    if payload.get("type") != "access":
        raise Unauthorized("Expected access token")
    user_id = payload.get("sub")
    if not user_id:
        raise Unauthorized("Token missing subject")
    user = await db.get(User, user_id)
    if user is None:
        raise Unauthorized("User not found")
    # Session epoch: a logout / password change bumps users.token_version, which
    # immediately invalidates every access token minted before the bump.
    if payload.get("tv", 0) != (user.token_version or 0):
        raise Unauthorized("Session expired, please log in again")
    return user


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise Unauthorized("Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    # Pick the verifier from the token's signature algorithm: Clerk session tokens
    # are RS256 (verified via JWKS), legacy app tokens are HS256 (jwt_secret).
    try:
        alg = jwt.get_unverified_header(token).get("alg")
    except Exception:
        raise Unauthorized("Malformed token") from None
    s = get_settings()
    if alg == "RS256" and s.clerk_enabled:
        return await _user_from_clerk_token(token, db)
    # Legacy HS256 (jwt_secret) is only honored when explicitly enabled or when
    # Clerk isn't configured. With Clerk on and legacy off, an HS256 token (forged
    # or a stale pre-Clerk session) must NOT be accepted — otherwise anyone who
    # learns jwt_secret could mint tokens alongside Clerk.
    if s.legacy_password_auth or not s.clerk_enabled:
        return await _user_from_legacy_token(token, db)
    raise Unauthorized("Invalid or expired token")


CurrentUser = Annotated[User, Depends(get_current_user)]
DB = Annotated[AsyncSession, Depends(get_db)]


async def get_optional_user(
    authorization: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Returns current user if authenticated, None otherwise.
    Used for public routes that have richer behavior when logged in."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    try:
        return await get_current_user(authorization=authorization, db=db)
    except Exception:
        return None


OptionalUser = Annotated[User | None, Depends(get_optional_user)]


async def get_user_story(story_id: str, user: CurrentUser, db: DB) -> Story:
    story = await db.get(Story, story_id)
    if story is None or story.user_id != user.id:
        raise NotFound(f"Story {story_id} not found")
    return story
