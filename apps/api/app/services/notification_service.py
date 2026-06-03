"""In-app notifications.

Currently one event type — a followed story posted a new chapter — fanned out to
every follower who hasn't opted out (PublicationFollow.notification_pref != "none").
Email delivery is a deliberate later add-on; the `notification_pref` field is
already shaped for it.
"""
from __future__ import annotations

import logging

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.publishing_models import Notification, Publication, PublicationFollow

log = logging.getLogger("gink.notify")


async def notify_new_chapters(
    db: AsyncSession,
    pub: Publication,
    story_title: str,
    new_chapters: list[tuple[int, str]],
) -> int:
    """Queue a 'new chapter' notification for each opted-in follower × new chapter.
    Adds rows to the caller's session (the publish route commits). Best-effort:
    swallows errors so a notification glitch never blocks publishing. Returns the
    number of notifications queued."""
    if not new_chapters:
        return 0
    try:
        followers = (await db.execute(
            select(PublicationFollow.reader_id)
            .where(PublicationFollow.publication_id == pub.id)
            .where(PublicationFollow.notification_pref != "none")
        )).scalars().all()
        if not followers:
            return 0

        count = 0
        for number, title in new_chapters:
            chap_title = (title or f"Chapter {number}").strip()
            for reader_id in followers:
                db.add(Notification(
                    user_id=reader_id,
                    kind="new_chapter",
                    publication_id=pub.id,
                    title=f"New chapter in “{story_title}”",
                    body=f"Chapter {number}: {chap_title}",
                    link=f"/read/{pub.slug}/{number}",
                ))
                count += 1
        return count
    except Exception:
        log.warning("failed to queue new-chapter notifications for pub %s", pub.id, exc_info=True)
        return 0


# ---------------------------------------------------------------------------
# Reader-facing queries
# ---------------------------------------------------------------------------

async def list_for_user(db: AsyncSession, user_id: str, *, limit: int = 30, unread_only: bool = False) -> dict:
    q = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        q = q.where(Notification.read == False)  # noqa: E712
    rows = (await db.execute(
        q.order_by(Notification.created_at.desc()).limit(limit)
    )).scalars().all()
    return {"items": [_serialize(n) for n in rows], "unread_count": await unread_count(db, user_id)}


async def unread_count(db: AsyncSession, user_id: str) -> int:
    return int((await db.execute(
        select(func.count()).select_from(Notification)
        .where(Notification.user_id == user_id)
        .where(Notification.read == False)  # noqa: E712
    )).scalar_one() or 0)


async def mark_read(db: AsyncSession, user_id: str, *, ids: list[str] | None = None, all_read: bool = False) -> int:
    stmt = update(Notification).where(Notification.user_id == user_id).values(read=True)
    if not all_read:
        if not ids:
            return 0
        stmt = stmt.where(Notification.id.in_(ids))
    res = await db.execute(stmt)
    return res.rowcount or 0


def _serialize(n: Notification) -> dict:
    return {
        "id": n.id,
        "kind": n.kind,
        "publication_id": n.publication_id,
        "title": n.title,
        "body": n.body,
        "link": n.link,
        "read": n.read,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }
