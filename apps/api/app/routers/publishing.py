from typing import Annotated

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import idempotency
from app.core.deps import get_current_user, get_db
from app.core.errors import envelope_ok
from app.db.models import User
from app.db.publishing_schemas import PublicationCreate, PublicationUpdate, PushChaptersRequest
from app.services import publishing_service as svc

router = APIRouter()


@router.post("/")
async def create_publication(
    payload: PublicationCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pub = await svc.create_publication(payload, user, db)
    await db.commit()
    return envelope_ok(pub)


@router.get("/")
async def list_publications(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pubs = await svc.list_writer_publications(user, db)
    return envelope_ok(pubs)


@router.get("/{story_id}")
async def get_publication(
    story_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pub = await svc.get_writer_publication(story_id, user, db)
    return envelope_ok(pub)


@router.put("/{pub_id}")
async def update_publication(
    pub_id: str,
    payload: PublicationUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pub = await svc.update_publication(pub_id, payload, user, db)
    await db.commit()
    return envelope_ok(pub)


@router.get("/{pub_id}/chapters")
async def list_pushed_chapters(
    pub_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the latest snapshot of every chapter pushed to this publication."""
    chapters = await svc.list_pushed_chapters(pub_id, user, db)
    return envelope_ok(chapters)


@router.post("/{pub_id}/push")
async def push_chapters(
    pub_id: str,
    req: PushChaptersRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: Annotated[str | None, Header()] = None,
):
    # Guard against a retried push creating redundant chapter versions.
    scope = f"publish.push:{pub_id}"
    replayed = await idempotency.replay(db, user.id, idempotency_key, scope)
    if replayed is not None:
        return envelope_ok(replayed)

    pushed = await svc.push_chapters(pub_id, req, user, db)
    await db.commit()
    result = {"pushed": len(pushed)}
    await idempotency.remember(db, user.id, idempotency_key, scope, result)
    return envelope_ok(result)


@router.post("/{pub_id}/go-live")
async def go_live(
    pub_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pub = await svc.go_live(pub_id, user, db)
    await db.commit()
    return envelope_ok(pub)


@router.post("/{pub_id}/unpublish")
async def unpublish(
    pub_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pub = await svc.unpublish(pub_id, user, db)
    await db.commit()
    return envelope_ok(pub)


@router.post("/{pub_id}/archive")
async def archive(
    pub_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pub = await svc.archive(pub_id, user, db)
    await db.commit()
    return envelope_ok(pub)


@router.delete("/{pub_id}")
async def delete_publication(
    pub_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await svc.delete_publication(pub_id, user, db)
    await db.commit()
    return envelope_ok({"deleted": True})
