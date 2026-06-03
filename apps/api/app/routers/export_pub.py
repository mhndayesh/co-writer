from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.deps import get_current_user, get_db
from app.db.models import User, Story, Chapter
from app.services.publishing_export_service import (
    export_pdf, export_epub, export_docx, export_submission_package,
)
from app.core.errors import NotFound, Forbidden

export_router = APIRouter()


async def _load_story_chapters(story_id: str, user: User, db: AsyncSession):
    story = await db.get(Story, story_id)
    if not story:
        raise NotFound("story")
    if story.user_id != user.id:
        raise Forbidden("not your story")
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


def _author_name(user: User) -> str:
    return user.display_name or user.email.split("@")[0]


@export_router.get("/{story_id}/pdf")
async def get_pdf(
    story_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    story, chs = await _load_story_chapters(story_id, user, db)
    data, fname, mime = export_pdf(story.title, _author_name(user), None, chs)
    return Response(content=data, media_type=mime,
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@export_router.get("/{story_id}/epub")
async def get_epub(
    story_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    story, chs = await _load_story_chapters(story_id, user, db)
    data, fname, mime = export_epub(story.title, _author_name(user), None,
                                    story.genre if story.genre else None, chs)
    return Response(content=data, media_type=mime,
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@export_router.get("/{story_id}/docx")
async def get_docx(
    story_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    story, chs = await _load_story_chapters(story_id, user, db)
    data, fname, mime = export_docx(story.title, _author_name(user), chs)
    return Response(content=data, media_type=mime,
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@export_router.get("/{story_id}/package")
async def get_package(
    story_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    story, chs = await _load_story_chapters(story_id, user, db)
    data, fname, mime = await export_submission_package(
        story.title, _author_name(user), None,
        story.genre if story.genre else None, chs,
    )
    return Response(content=data, media_type=mime,
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})
