# ARQ background worker for export tasks + scheduled maintenance.
# Launch with: arq app.workers.export_worker.WorkerSettings
#
# Requires REDIS_URL env var.

from __future__ import annotations

import logging
from typing import Any

from arq import cron
from sqlalchemy import select

from app.db.models import Story, Chapter
from app.db.session import SessionLocal
from app.services import graph_service
from app.services.publishing_export_service import export_pdf, export_epub

log = logging.getLogger("gink.worker")


async def _load_chapters(story_id: str, user_id: str, db) -> tuple[Any, list[dict]]:
    story = await db.get(Story, story_id)
    if not story or story.user_id != user_id:
        raise ValueError(f"story {story_id} not found or not owned by user {user_id}")

    chapters = (await db.execute(
        select(Chapter)
        .where(Chapter.story_id == story_id)
        .order_by(Chapter.number)
    )).scalars().all()

    ch_list = [
        {"number": c.number, "title": c.title or f"Chapter {c.number}", "content": c.content or ""}
        for c in chapters if c.content
    ]
    return story, ch_list


async def export_pdf_task(ctx: dict, story_id: str, user_id: str, author_name: str) -> dict:
    async with SessionLocal() as db:
        story, chs = await _load_chapters(story_id, user_id, db)

    data, fname, mime = export_pdf(story.title, author_name, None, chs)

    redis = ctx["redis"]
    cache_key = f"export:{story_id}:pdf"
    await redis.setex(cache_key, 300, data)  # 5-minute TTL
    return {"ready": True, "key": cache_key, "filename": fname, "mime": mime}


async def export_epub_task(ctx: dict, story_id: str, user_id: str, author_name: str) -> dict:
    async with SessionLocal() as db:
        story, chs = await _load_chapters(story_id, user_id, db)

    data, fname, mime = export_epub(story.title, author_name, None, story.genre or None, chs)

    redis = ctx["redis"]
    cache_key = f"export:{story_id}:epub"
    await redis.setex(cache_key, 300, data)
    return {"ready": True, "key": cache_key, "filename": fname, "mime": mime}


async def reconcile_graphs_task(ctx: dict) -> dict:
    """Scheduled self-heal for stories whose Neo4j projection is stale.

    Runs on a cron; retries any story left with graph_status != "ok" (e.g. Neo4j
    was down during Flow approve). No-op when Neo4j is unreachable, so it's safe
    to fire on a timer regardless of Neo4j's state."""
    result = await graph_service.reconcile_stale_graphs(limit=50)
    if result.get("reconciled"):
        log.info("graph reconcile healed %s stories", result["reconciled"])
    return result


async def prune_idempotency_task(ctx: dict) -> dict:
    """Scheduled cleanup so idempotency_keys can't grow unbounded (a key only
    matters for the brief retry window after an operation)."""
    from app.core import idempotency
    async with SessionLocal() as db:
        deleted = await idempotency.prune_expired(db, max_age_days=7)
    if deleted:
        log.info("pruned %s expired idempotency keys", deleted)
    return {"pruned": deleted}


class WorkerSettings:
    functions = [export_pdf_task, export_epub_task]
    cron_jobs = [
        # Every 5 minutes, repair any drifted Neo4j projections (graph self-heal).
        cron(reconcile_graphs_task, minute=set(range(0, 60, 5))),
        # Daily at 03:17, prune stale idempotency rows.
        cron(prune_idempotency_task, hour={3}, minute={17}),
    ]
    # Read REDIS_URL from config — `RedisSettings()` alone defaults to localhost,
    # so the worker would connect nowhere in the standard compose topology.
    from app.workers import redis_settings as _redis_settings
    redis_settings = _redis_settings()
