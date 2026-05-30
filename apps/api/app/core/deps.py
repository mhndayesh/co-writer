from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound, Unauthorized
from app.core.security import decode_token
from app.db.models import Story, User
from app.db.session import get_db


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise Unauthorized("Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
    except Exception as e:
        raise Unauthorized(f"Invalid token: {e}") from e
    if payload.get("type") != "access":
        raise Unauthorized("Expected access token")
    user_id = payload.get("sub")
    if not user_id:
        raise Unauthorized("Token missing subject")
    user = await db.get(User, user_id)
    if user is None:
        raise Unauthorized("User not found")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
DB = Annotated[AsyncSession, Depends(get_db)]


async def get_user_story(story_id: str, user: CurrentUser, db: DB) -> Story:
    story = await db.get(Story, story_id)
    if story is None or story.user_id != user.id:
        raise NotFound(f"Story {story_id} not found")
    return story
