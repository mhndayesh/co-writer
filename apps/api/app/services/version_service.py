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
    CharacterVoiceProfile,
    Faction,
    Location,
    PlotThread,
    PlotThreadSceneLink,
    Revelation,
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
    revelations = (await db.execute(select(Revelation).where(Revelation.story_id == story_id))).scalars().all()
    thread_scene_links = (await db.execute(select(PlotThreadSceneLink).where(PlotThreadSceneLink.story_id == story_id))).scalars().all()
    voice_profiles = (await db.execute(select(CharacterVoiceProfile).where(CharacterVoiceProfile.story_id == story_id))).scalars().all()

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
        "locations": [
            {"id": loc.id, "name": loc.name, "description": loc.description, "visual": loc.visual}
            for loc in locs
        ],
        "factions": [{"id": f.id, "name": f.name, "description": f.description, "visual_signature": f.visual_signature} for f in facs],
        "themes": [{"id": t.id, "name": t.name, "description": t.description} for t in themes],
        "threads": [
            {"id": t.id, "name": t.name, "status": t.status, "description": t.description, "chapter_ids": list(t.chapter_ids or [])}
            for t in threads
        ],
        "scenes": [
            {
                "id": s.id,
                "chapter_id": s.chapter_id,
                "ordinal": s.ordinal,
                "beat": s.beat,
                "title": s.title,
                "summary": s.summary,
                "goal": s.goal,
                "conflict": s.conflict,
                "outcome": s.outcome,
                "pov": s.pov_character_id,
                "location": s.location_id,
                "characters": list(s.character_ids or []),
                "plot_threads": list(s.plot_thread_ids or []),
                "time_anchor": s.time_anchor,
                "time_sort_key": s.time_sort_key,
                "duration_hint": s.duration_hint,
                "sensory_palette": dict(s.sensory_palette or {}),
                "source_excerpt": s.source_excerpt,
                "content": s.content,
            }
            for s in scenes
        ],
        "revelations": [
            {
                "id": r.id,
                "scene_id": r.scene_id,
                "chapter_id": r.chapter_id,
                "description": r.description,
                "kind": r.kind,
                "characters_who_know": list(r.characters_who_know or []),
                "reader_knows": r.reader_knows,
                "notes": r.notes,
                "confidence": r.confidence,
            }
            for r in revelations
        ],
        "thread_scene_links": [
            {
                "id": link.id,
                "thread_id": link.thread_id,
                "scene_id": link.scene_id,
                "chapter_id": link.chapter_id,
                "status": link.status,
                "strength": link.strength,
                "evidence": link.evidence,
            }
            for link in thread_scene_links
        ],
        "voice_profiles": [
            {
                "id": p.id,
                "character_id": p.character_id,
                "sample_count": p.sample_count,
                "dialogue_words": p.dialogue_words,
                "avg_sentence_words": p.avg_sentence_words,
                "question_rate": p.question_rate,
                "exclamation_rate": p.exclamation_rate,
                "vocabulary_variety": p.vocabulary_variety,
                "dialogue_share": p.dialogue_share,
                "repeated_phrases": list(p.repeated_phrases or []),
                "stats": dict(p.stats or {}),
            }
            for p in voice_profiles
        ],
    }

    last_no = await db.scalar(select(func.coalesce(func.max(StoryVersion.version_no), 0)).where(StoryVersion.story_id == story_id)) or 0
    version = StoryVersion(story_id=story_id, version_no=int(last_no) + 1, snapshot=snap, note=note)
    db.add(version)
    await db.flush()
    return version
