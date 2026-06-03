"""Legacy email+password auth — RETIRED in favor of Clerk.

These routes are only mounted when `settings.legacy_password_auth` is true
(see app/main.py). The production app authenticates through Clerk; this module
exists for the test suite and for deployments still mid-migration. The minted
tokens are HS256, which get_current_user still accepts alongside Clerk's RS256.
"""
from fastapi import APIRouter, Request
from sqlalchemy import select

from app.core.deps import CurrentUser, DB
from app.core.errors import Conflict, Unauthorized, envelope_ok
from app.core.ratelimit import limiter
from app.core.security import hash_password, verify_password
from app.db.models import User
from app.db.schemas import LoginRequest, SignupRequest, UserOut
from app.services import auth_service

router = APIRouter()


# Per-route throttles guard credential stuffing / brute force / mass signup. The
# `request: Request` param is required by SlowAPI to key on the client IP. These
# are no-ops in development/tests (the limiter is disabled there).
@router.post("/signup")
@limiter.limit("10/hour")
async def signup(request: Request, payload: SignupRequest, db: DB):
    existing = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if existing is not None:
        raise Conflict("Email already registered")
    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name or payload.email.split("@")[0],
    )
    db.add(user)
    await db.flush()  # assign user.id before minting the refresh-token row
    tokens = await auth_service.issue_token_pair(db, user)
    await db.commit()
    return envelope_ok({"user": UserOut.model_validate(user).model_dump(mode="json"), "tokens": tokens.model_dump()})


@router.post("/login")
@limiter.limit("10/minute")
async def login(request: Request, payload: LoginRequest, db: DB):
    user = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if user is None or not user.password_hash or not verify_password(payload.password, user.password_hash):
        raise Unauthorized("Invalid email or password")
    tokens = await auth_service.issue_token_pair(db, user)
    await db.commit()
    return envelope_ok({"user": UserOut.model_validate(user).model_dump(mode="json"), "tokens": tokens.model_dump()})


@router.post("/refresh")
@limiter.limit("30/minute")
async def refresh(request: Request, payload: dict, db: DB):
    tokens = await auth_service.rotate(db, payload.get("refresh_token", ""))
    await db.commit()
    return envelope_ok({"tokens": tokens.model_dump()})


@router.post("/logout")
async def logout(user: CurrentUser, db: DB):
    """End all sessions: revoke the user's refresh tokens and invalidate every
    outstanding access token (via a token_version bump)."""
    await auth_service.logout(db, user)
    await db.commit()
    return envelope_ok({"logged_out": True})
