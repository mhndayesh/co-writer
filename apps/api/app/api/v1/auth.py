"""Auth routes.

Identity is owned by Clerk (see app/core/deps.py + app/services/clerk_service.py).
The legacy password endpoints (signup/login/refresh/logout) have been retired —
sign-in/up happen client-side via Clerk, session tokens are minted by Clerk, and
sign-out is a client-side Clerk action. Only the authenticated `me` lookup
remains, used by the frontend to resolve the local user row behind a Clerk token.
"""
from fastapi import APIRouter

from app.core.deps import CurrentUser
from app.core.errors import envelope_ok
from app.db.schemas import UserOut

router = APIRouter()


@router.get("/me")
async def me(user: CurrentUser):
    return envelope_ok({"user": UserOut.model_validate(user).model_dump(mode="json")})
