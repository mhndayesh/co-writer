# Async export submit-and-poll endpoints.
# The synchronous endpoints in app/routers/export_pub.py remain working.
# These async endpoints are an optional upgrade for heavy PDF/EPUB exports.

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, get_user_story
from app.core.errors import envelope_ok, NotFound
from app.db.models import User

router = APIRouter()


@router.post("/{story_id}/pdf/submit")
async def submit_pdf_export(
    story_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_user_story(story_id, user, db)  # 404 for foreign/missing story (IDOR guard)
    try:
        import arq
        from app.workers import redis_settings
        pool = await arq.create_pool(redis_settings())
        job = await pool.enqueue_job("export_pdf_task", story_id, user.id,
                                     user.display_name or user.email.split("@")[0])
        await pool.aclose()
        return envelope_ok({"job_id": job.job_id})
    except Exception as exc:
        raise NotFound(f"Export queue unavailable: {exc}") from exc


@router.get("/{story_id}/pdf/status/{job_id}")
async def check_pdf_export(
    story_id: str, job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_user_story(story_id, user, db)  # 404 for foreign/missing story (IDOR guard)
    try:
        import arq
        from app.workers import redis_settings
        pool = await arq.create_pool(redis_settings())
        job = arq.jobs.Job(job_id, pool)
        status = await job.status()
        result = await job.result(timeout=0) if str(status) == "complete" else None
        await pool.aclose()

        if result and result.get("ready"):
            return envelope_ok({
                "ready": True,
                "download_url": f"/v1/export/{story_id}/pdf",
            })
        return envelope_ok({"ready": False, "status": str(status)})
    except Exception as exc:
        return envelope_ok({"ready": False, "status": "error", "detail": str(exc)})


@router.get("/{story_id}/epub/submit")
async def submit_epub_export(
    story_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_user_story(story_id, user, db)  # 404 for foreign/missing story (IDOR guard)
    try:
        import arq
        from app.workers import redis_settings
        pool = await arq.create_pool(redis_settings())
        job = await pool.enqueue_job("export_epub_task", story_id, user.id,
                                     user.display_name or user.email.split("@")[0])
        await pool.aclose()
        return envelope_ok({"job_id": job.job_id})
    except Exception as exc:
        raise NotFound(f"Export queue unavailable: {exc}") from exc
