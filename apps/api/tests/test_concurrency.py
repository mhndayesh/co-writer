"""Batch-B regression tests: optimistic locking + relationship uniqueness.

These guard the data-integrity fixes from the e2e audit:
- chapter/scene/character carry a version_id_col, so a concurrent read-modify-write
  raises StaleDataError (the API maps it to 409) instead of silently clobbering.
- character_relationships enforces one row per (story, source, target).
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

import app.db.models as m
from app.db.session import SessionLocal


@pytest_asyncio.fixture()
async def seeded():
    """A user + story + chapter + two characters; returns their ids.

    Unique email per invocation — the suite's SQLite file persists across tests,
    so a fixed address would collide on the users.email unique constraint."""
    async with SessionLocal() as s:
        u = m.User(email=f"concurrency-{uuid.uuid4().hex}@example.com")
        s.add(u)
        await s.flush()
        st = m.Story(user_id=u.id, title="Lock Test")
        s.add(st)
        await s.flush()
        ch = m.Chapter(story_id=st.id, number=1, title="ch", content="orig")
        a = m.Character(story_id=st.id, name="A")
        b = m.Character(story_id=st.id, name="B")
        s.add_all([ch, a, b])
        await s.commit()
        return {"story": st.id, "chapter": ch.id, "a": a.id, "b": b.id}


@pytest.mark.asyncio
async def test_concurrent_chapter_edit_raises_stale_data(seeded):
    s1 = SessionLocal()
    s2 = SessionLocal()
    try:
        c1 = await s1.get(m.Chapter, seeded["chapter"])
        c2 = await s2.get(m.Chapter, seeded["chapter"])  # both read version 1
        c1.content = "edit from tab 1"
        await s1.commit()                                 # bumps to version 2
        c2.content = "edit from tab 2"
        with pytest.raises(StaleDataError):
            await s2.commit()                             # WHERE version_id=1 → 0 rows
    finally:
        await s1.close()
        await s2.close()


@pytest.mark.asyncio
async def test_duplicate_relationship_pair_rejected(seeded):
    async with SessionLocal() as s:
        s.add(m.CharacterRelationship(
            story_id=seeded["story"], source_id=seeded["a"], target_id=seeded["b"], type="ally"))
        await s.commit()
    with pytest.raises(IntegrityError):
        async with SessionLocal() as s:
            s.add(m.CharacterRelationship(
                story_id=seeded["story"], source_id=seeded["a"], target_id=seeded["b"], type="enemy"))
            await s.commit()
