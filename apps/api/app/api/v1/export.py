from fastapi import APIRouter
from fastapi.responses import Response

from app.core.deps import CurrentUser, DB, get_user_story
from app.core.errors import envelope_ok
from app.services import export_service

router = APIRouter()


@router.get("/{story_id}/export/markdown")
async def export_markdown(story_id: str, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    md = await export_service.story_to_markdown(db, story_id)
    return Response(content=md, media_type="text/markdown", headers={"Content-Disposition": f'attachment; filename="story_{story_id}.md"'})


@router.get("/{story_id}/export/bundle")
async def export_bundle(story_id: str, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    bundle = await export_service.story_to_bundle(db, story_id)
    return envelope_ok(bundle)


@router.get("/{story_id}/export/docx")
async def export_docx(story_id: str, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    data = await export_service.story_to_docx_bytes(db, story_id)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="story_{story_id}.docx"'},
    )


@router.post("/import")
async def import_bundle(payload: dict, user: CurrentUser, db: DB):
    story_id = await export_service.import_bundle(db, user.id, payload)
    return envelope_ok({"story_id": story_id})
