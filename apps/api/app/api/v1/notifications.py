"""Reader-facing in-app notifications (bell + library page)."""
from fastapi import APIRouter, Query

from app.core.deps import CurrentUser, DB
from app.core.errors import envelope_ok
from app.services import notification_service as nsvc

router = APIRouter()


@router.get("")
async def list_notifications(
    user: CurrentUser,
    db: DB,
    limit: int = Query(30, ge=1, le=100),
    unread_only: bool = Query(False),
):
    return envelope_ok(await nsvc.list_for_user(db, user.id, limit=limit, unread_only=unread_only))


@router.get("/unread-count")
async def unread_count(user: CurrentUser, db: DB):
    return envelope_ok({"unread_count": await nsvc.unread_count(db, user.id)})


@router.post("/read")
async def mark_read(payload: dict, user: CurrentUser, db: DB):
    payload = payload or {}
    n = await nsvc.mark_read(
        db, user.id,
        ids=payload.get("ids"),
        all_read=bool(payload.get("all")),
    )
    await db.commit()
    return envelope_ok({"marked": n})
