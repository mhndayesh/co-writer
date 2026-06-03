from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.errors import envelope_ok
from app.db.models import User
from app.services.social_service import get_writer_inbox, get_unread_count

inbox_router = APIRouter()


@inbox_router.get("/")
async def inbox(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await get_writer_inbox(user, db)
    return envelope_ok(data)


@inbox_router.get("/unread-count")
async def unread(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    count = await get_unread_count(user, db)
    return envelope_ok({"count": count})
