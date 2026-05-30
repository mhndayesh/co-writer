"""Snapshot a story's full state into the immutable story_versions table.

Snapshot shape matches Story_Forge_Docs.md §6 + production-stage entities,
so a `story_versions.snapshot` is interchangeable with a Story Forge
backup JSON.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Chapter,
    Character,
    CharacterRelationship,
    Faction,
    Location,
    PlotThread,
    SceneCard,
    Story,
    StoryVersion,
    Theme,
    World,
)


async def snapshot(db: AsyncSession, story_id: str, *, note: str = "") -> StoryVersion:
    story = await db.get(Story, story_id)
    world = await db.get(World, story_id)
    chars = (await db.execute(select(Character).where(Character.story_id == story_id))).scalars().all()
    rels = (await db.execute(select(CharacterRelationship).where(CharacterRelationship.story_id == story_id))).scalars().all()
    chaps = (await db.execute(select(Chapter).where(Chapter.story_id == story_id).order_by(Chapter.number))).scalars().all()
    locs = (await db.execute(select(Location).where(Location.story_id == story_id))).scalars().all()
    facs = (await db.execute(select(Faction).where(Faction.story_id == story_id))).scalars().all()
    themes = (await db.execute(select(Theme).where(Theme.story_id == story_id))).scalars().all()
    threads = (await db.execute(select(PlotThread).where(PlotThread.story_id == story_id))).scalars().all()
    scenes = (await db.execute(select(SceneCard).where(SceneCard.story_id == story_id))).scalars().all()

    def char_to_dict(c: Character) -> dict:
        return {
            "id": c.id, "name": c.name, "role": c.role, "icon": c.icon, "age": c.age,
            "appearance": c.appearance, "personality": c.personality, "backstory": c.backstory,
            "motivation": c.motivation, "flaw": c.flaw, "arc": c.arc, "status": c.status,
            "relationships": [
                {"target_id": r.target_id, "type": r.type, "description": r.description}
                for r in rels if r.source_id == c.id
            ],
        }

    snap = {
        "world": {
            "title": (world.title if world else story.title) or "",
            "genre": (world.genre if world else story.genre) or "",
            "logline": world.logline if world else "",
            "time_period": world.time_period if world else "",
            "setting": world.setting if world else "",
            "rules": list(world.rules or []) if world else [],
            "themes": list(world.themes or []) if world else [],
            "lore": world.lore if world else "",
            "seeds": world.seeds if world else "",
        },
        "chars": [char_to_dict(c) for c in chars],
        "chaps": [
            {
                "id": c.id, "number": c.number, "title": c.title, "content": c.content,
                "summary": c.summary, "pov": c.pov_character_id, "location": c.location_id,
                "characters": list(c.character_ids or []), "seeds": c.seeds or [],
            }
            for c in chaps
        ],
        "locations": [{"id": l.id, "name": l.name, "description": l.description, "visual": l.visual} for l in locs],
        "factions": [{"id": f.id, "name": f.name, "description": f.description, "visual_signature": f.visual_signature} for f in facs],
        "themes": [{"id": t.id, "name": t.name, "description": t.description} for t in themes],
        "threads": [
            {"id": t.id, "name": t.name, "status": t.status, "description": t.description, "chapter_ids": list(t.chapter_ids or [])}
            for t in threads
        ],
        "scenes": [
            {"id": s.id, "chapter_id": s.chapter_id, "ordinal": s.ordinal, "beat": s.beat, "content": s.content}
            for s in scenes
        ],
    }

    last_no = await db.scalar(select(func.coalesce(func.max(StoryVersion.version_no), 0)).where(StoryVersion.story_id == story_id)) or 0
    version = StoryVersion(story_id=story_id, version_no=int(last_no) + 1, snapshot=snap, note=note)
    db.add(version)
    await db.flush()
    return version
