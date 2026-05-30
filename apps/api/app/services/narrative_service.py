"""Read models for scene-first narrative intelligence."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chapter, Character, Location, PlotThread, PlotThreadSceneLink, Revelation, SceneCard
from app.db.schemas import TimelineSceneOut, WeaveCellOut, WeaveOut, WeaveThreadOut


async def _story_lookup(db: AsyncSession, story_id: str) -> dict:
    chapters = (await db.execute(select(Chapter).where(Chapter.story_id == story_id).order_by(Chapter.number))).scalars().all()
    characters = (await db.execute(select(Character).where(Character.story_id == story_id))).scalars().all()
    locations = (await db.execute(select(Location).where(Location.story_id == story_id))).scalars().all()
    threads = (await db.execute(select(PlotThread).where(PlotThread.story_id == story_id))).scalars().all()
    return {
        "chapters": {c.id: c for c in chapters},
        "characters": {c.id: c for c in characters},
        "locations": {loc.id: loc for loc in locations},
        "threads": {t.id: t for t in threads},
        "chapter_order": {c.id: i for i, c in enumerate(chapters)},
    }


def _reading_key(scene: SceneCard, lookup: dict) -> tuple[int, int, str]:
    chapter = lookup["chapters"].get(scene.chapter_id or "")
    number = chapter.number if chapter else 999999
    return (number, scene.ordinal, scene.id)


def _timeline_scene(scene: SceneCard, lookup: dict) -> TimelineSceneOut:
    chapter = lookup["chapters"].get(scene.chapter_id or "")
    pov = lookup["characters"].get(scene.pov_character_id or "")
    loc = lookup["locations"].get(scene.location_id or "")
    threads = lookup["threads"]
    chars = lookup["characters"]
    return TimelineSceneOut(
        **{
            "id": scene.id,
            "story_id": scene.story_id,
            "chapter_id": scene.chapter_id,
            "ordinal": scene.ordinal,
            "beat": scene.beat,
            "title": scene.title,
            "summary": scene.summary,
            "goal": scene.goal,
            "conflict": scene.conflict,
            "outcome": scene.outcome,
            "pov_character_id": scene.pov_character_id,
            "location_id": scene.location_id,
            "character_ids": list(scene.character_ids or []),
            "plot_thread_ids": list(scene.plot_thread_ids or []),
            "time_anchor": scene.time_anchor,
            "time_sort_key": scene.time_sort_key,
            "duration_hint": scene.duration_hint,
            "sensory_palette": dict(scene.sensory_palette or {}),
            "source_excerpt": scene.source_excerpt,
            "content": scene.content,
            "chapter_number": chapter.number if chapter else None,
            "chapter_title": chapter.title if chapter else "",
            "pov_name": pov.name if pov else "",
            "location_name": loc.name if loc else "",
            "character_names": [chars[cid].name for cid in (scene.character_ids or []) if cid in chars],
            "plot_thread_names": [threads[tid].name for tid in (scene.plot_thread_ids or []) if tid in threads],
        }
    )


async def timeline(db: AsyncSession, story_id: str, *, order: str = "story") -> list[TimelineSceneOut]:
    lookup = await _story_lookup(db, story_id)
    scenes = (await db.execute(select(SceneCard).where(SceneCard.story_id == story_id))).scalars().all()
    reading_order = sorted(scenes, key=lambda s: _reading_key(s, lookup))
    reading_index = {s.id: i for i, s in enumerate(reading_order)}

    if order == "reading":
        ordered = reading_order
    else:
        ordered = sorted(
            scenes,
            key=lambda s: (
                0 if s.time_sort_key is not None else 1,
                s.time_sort_key if s.time_sort_key is not None else reading_index.get(s.id, 0),
                _reading_key(s, lookup),
            ),
        )
    return [_timeline_scene(s, lookup) for s in ordered]


async def weave(db: AsyncSession, story_id: str) -> WeaveOut:
    lookup = await _story_lookup(db, story_id)
    scenes_raw = (await db.execute(select(SceneCard).where(SceneCard.story_id == story_id))).scalars().all()
    scenes_raw = sorted(scenes_raw, key=lambda s: _reading_key(s, lookup))
    scene_index = {s.id: i for i, s in enumerate(scenes_raw)}
    scenes = [_timeline_scene(s, lookup) for s in scenes_raw]
    threads = list(lookup["threads"].values())

    links = (await db.execute(select(PlotThreadSceneLink).where(PlotThreadSceneLink.story_id == story_id))).scalars().all()
    explicit = {(link.thread_id, link.scene_id): link for link in links}

    out_threads: list[WeaveThreadOut] = []
    for thread in threads:
        cells: list[WeaveCellOut] = []
        for scene in scenes_raw:
            link = explicit.get((thread.id, scene.id))
            if link is None and thread.id not in (scene.plot_thread_ids or []):
                continue
            chapter = lookup["chapters"].get(scene.chapter_id or "")
            cells.append(WeaveCellOut(
                scene_id=scene.id,
                chapter_id=scene.chapter_id,
                chapter_number=chapter.number if chapter else None,
                scene_ordinal=scene.ordinal,
                scene_title=scene.title or scene.beat or scene.summary[:60],
                status=link.status if link else "touch",
                strength=link.strength if link else 1.0,
                evidence=link.evidence if link else "",
            ))
        dormant_after = None
        if cells:
            last_idx = max(scene_index.get(c.scene_id, 0) for c in cells)
            dormant_after = max(0, len(scenes_raw) - last_idx - 1)
        out_threads.append(WeaveThreadOut(
            thread_id=thread.id,
            name=thread.name,
            status=thread.status,
            description=thread.description,
            cells=cells,
            dormant_after=dormant_after,
        ))

    return WeaveOut(threads=out_threads, scenes=scenes)


async def list_revelations(db: AsyncSession, story_id: str) -> list[Revelation]:
    return (
        await db.execute(
            select(Revelation)
            .where(Revelation.story_id == story_id)
            .order_by(Revelation.created_at, Revelation.id)
        )
    ).scalars().all()
