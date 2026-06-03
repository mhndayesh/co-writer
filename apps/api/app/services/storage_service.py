"""Local image storage for cover uploads.

Images are validated + RE-ENCODED through Pillow (which neutralizes polyglot /
exploit payloads and strips EXIF), written under a content-addressable-ish uuid
name, and served back at /v1/uploads/<file> (same-origin, so it passes the reader
CSP's `img-src 'self'`).

This is deliberately a thin, swappable layer: `save_image` is the only thing the
rest of the app calls, so a future S3/R2 backend is a drop-in replacement.
"""
from __future__ import annotations

import io
import uuid
from pathlib import Path

from PIL import Image

from app.core.config import get_settings
from app.core.errors import BadRequest

# Pillow format → (extension, save kwargs). We normalize everything to one of
# these on re-encode; anything else (incl. SVG, which Pillow won't open) is rejected.
_ALLOWED = {
    "PNG":  ("png",  {"optimize": True}),
    "JPEG": ("jpg",  {"quality": 85, "optimize": True}),
    "WEBP": ("webp", {"quality": 85, "method": 4}),
    "GIF":  ("gif",  {"save_all": True}),  # keep animation
}
_MAX_DIM = 2400  # px — downscale anything larger (covers don't need more)
# Files are SERVED here (StaticFiles mount in main.py); the UPLOAD endpoint is
# /v1/uploads/image — kept on a separate path so the mount can't shadow the route.
URL_PREFIX = "/v1/media"


def resolve_upload_dir() -> Path:
    """Absolute uploads dir. Defaults to <api-pkg>/uploads when UPLOAD_DIR is blank
    (mirrors the .env anchoring so cwd never matters)."""
    configured = get_settings().upload_dir.strip()
    if configured:
        d = Path(configured)
    else:
        d = Path(__file__).resolve().parents[2] / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_image(data: bytes) -> str:
    """Validate + re-encode an uploaded image and persist it. Returns the
    same-origin URL path (/v1/uploads/<file>). Raises BadRequest on anything that
    isn't a real, supported raster image."""
    max_bytes = get_settings().max_image_upload_mb * 1024 * 1024
    if not data:
        raise BadRequest("Empty file.")
    if len(data) > max_bytes:
        raise BadRequest(f"Image exceeds the {get_settings().max_image_upload_mb} MB limit.")

    try:
        img = Image.open(io.BytesIO(data))
        img.verify()  # integrity check (consumes the object)
        img = Image.open(io.BytesIO(data))  # reopen for actual processing
    except Exception as exc:
        raise BadRequest("That file is not a valid image.") from exc

    fmt = (img.format or "").upper()
    if fmt not in _ALLOWED:
        raise BadRequest("Unsupported image type — use PNG, JPEG, WEBP, or GIF.")

    ext, save_kwargs = _ALLOWED[fmt]
    is_animated = fmt == "GIF" and getattr(img, "is_animated", False)

    # Downscale oversized stills (skip animated GIFs to preserve frames).
    if not is_animated and max(img.size) > _MAX_DIM:
        img.thumbnail((_MAX_DIM, _MAX_DIM))

    # Flatten alpha for JPEG; otherwise re-encode in place (strips metadata).
    if fmt == "JPEG" and img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    name = f"{uuid.uuid4().hex}.{ext}"
    out_path = resolve_upload_dir() / name
    buf = io.BytesIO()
    img.save(buf, format=fmt, **save_kwargs)
    out_path.write_bytes(buf.getvalue())

    return f"{URL_PREFIX}/{name}"
