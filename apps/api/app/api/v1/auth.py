from fastapi import APIRouter
from sqlalchemy import select

from app.core.deps import CurrentUser, DB
from app.core.errors import Conflict, Unauthorized, envelope_ok
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.models import User
from app.db.schemas import LoginRequest, SignupRequest, TokenPair, UserOut

router = APIRouter()


@router.post("/signup")
async def signup(payload: SignupRequest, db: DB):
    existing = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if existing is not None:
        raise Conflict("Email already registered")
    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name or payload.email.split("@")[0],
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    tokens = TokenPair(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )
    return envelope_ok({"user": UserOut.model_validate(user).model_dump(mode="json"), "tokens": tokens.model_dump()})


@router.post("/login")
async def login(payload: LoginRequest, db: DB):
    user = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise Unauthorized("Invalid email or password")
    tokens = TokenPair(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )
    return envelope_ok({"user": UserOut.model_validate(user).model_dump(mode="json"), "tokens": tokens.model_dump()})


@router.post("/refresh")
async def refresh(payload: dict, db: DB):
    token = payload.get("refresh_token", "")
    try:
        claims = decode_token(token)
    except Exception as e:
        raise Unauthorized(f"Invalid refresh token: {e}") from e
    if claims.get("type") != "refresh":
        raise Unauthorized("Not a refresh token")
    user_id = claims.get("sub")
    if not user_id or (await db.get(User, user_id)) is None:
        raise Unauthorized("User not found")
    tokens = TokenPair(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
    )
    return envelope_ok({"tokens": tokens.model_dump()})


@router.get("/me")
async def me(user: CurrentUser):
    return envelope_ok({"user": UserOut.model_validate(user).model_dump(mode="json")})
