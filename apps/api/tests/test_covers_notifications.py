"""Covers + in-app notifications (hub/publishing feature)."""
import io
import uuid

import pytest
import pytest_asyncio
from PIL import Image

import app.db.models as m
import app.db.publishing_models as pm
from app.core.errors import BadRequest
from app.db.session import SessionLocal
from app.services import notification_service as nsvc
from app.services import reader_service as rsvc
from app.services import storage_service


def test_save_image_reencodes_and_rejects_junk(tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    storage_service.get_settings.cache_clear()  # pick up the patched UPLOAD_DIR
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), (10, 20, 30)).save(buf, format="PNG")
    url = storage_service.save_image(buf.getvalue())
    assert url.startswith("/v1/media/") and url.endswith(".png")
    assert (tmp_path / url.split("/")[-1]).stat().st_size > 0
    with pytest.raises(BadRequest):
        storage_service.save_image(b"definitely not an image")
    storage_service.get_settings.cache_clear()


@pytest_asyncio.fixture()
async def published_pub():
    """A writer + story + published publication, and a follower; returns ids."""
    async with SessionLocal() as s:
        writer = m.User(email=f"writer-{uuid.uuid4().hex}@x.z")
        reader = m.User(email=f"reader-{uuid.uuid4().hex}@x.z")
        s.add_all([writer, reader])
        await s.flush()
        story = m.Story(user_id=writer.id, title="The Saved Story")
        s.add(story)
        await s.flush()
        pub = pm.Publication(story_id=story.id, user_id=writer.id,
                             slug=f"saved-{uuid.uuid4().hex[:8]}", status="published")
        s.add(pub)
        await s.flush()
        s.add(pm.PublicationFollow(reader_id=reader.id, publication_id=pub.id))
        await s.commit()
        return {"reader": reader.id, "pub_id": pub.id, "slug": pub.slug, "story_title": story.title}


@pytest.mark.asyncio
async def test_new_chapter_notifies_followers(published_pub):
    async with SessionLocal() as s:
        pub = await s.get(pm.Publication, published_pub["pub_id"])
        n = await nsvc.notify_new_chapters(s, pub, published_pub["story_title"], [(2, "The Reveal")])
        await s.commit()
        assert n == 1

    async with SessionLocal() as s:
        feed = await nsvc.list_for_user(s, published_pub["reader"])
        assert feed["unread_count"] == 1
        item = feed["items"][0]
        assert "The Saved Story" in item["title"]
        assert item["body"] == "Chapter 2: The Reveal"
        assert item["link"] == f"/read/{published_pub['slug']}/2"

        # mark all read → count drops to 0
        await nsvc.mark_read(s, published_pub["reader"], all_read=True)
        await s.commit()
        assert (await nsvc.unread_count(s, published_pub["reader"])) == 0


@pytest.mark.asyncio
async def test_followed_story_shows_in_library_without_reading(published_pub):
    async with SessionLocal() as s:
        lib = await rsvc.get_reader_library(published_pub["reader"], s)
    slugs = [x["slug"] for x in lib["following"]]
    assert published_pub["slug"] in slugs  # saved without ever opening a chapter
