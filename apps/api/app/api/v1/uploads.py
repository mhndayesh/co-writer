"""Authenticated image upload for cover art (stories, chapters, publications).

POST /v1/uploads/image  (multipart) → {"url": "/v1/uploads/<file>"}
The file is validated + re-encoded by storage_service; the returned URL is then
saved onto whatever entity the caller is editing (Story/Chapter/Publication cover).
Static serving of /v1/uploads/<file> is mounted in main.py.
"""
from fastapi import APIRouter, Request, UploadFile, File

from app.core.deps import CurrentUser
from app.core.errors import envelope_ok, BadRequest
from app.core.ratelimit import limiter
from app.services import storage_service

router = APIRouter()


@router.post("/image")
@limiter.limit("30/minute")
async def upload_image(request: Request, user: CurrentUser, file: UploadFile = File(...)):
    if file.content_type and not file.content_type.startswith("image/"):
        raise BadRequest("Only image files are allowed.")
    data = await file.read()
    url = storage_service.save_image(data)  # validates + re-encodes; raises BadRequest on junk
    return envelope_ok({"url": url})
