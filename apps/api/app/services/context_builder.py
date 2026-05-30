"""Build the structured story context the LLM sees on every call.

Mirror of Story_Forge_Docs.md §5.2: `buildCtx(world, chars, chaps)` —
extended to include locations, factions, themes, and (optionally) a
Graph-RAG slice built from Qdrant + Neo4j (see rag_service).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Chapter,
    Character,
    CharacterRelationship,
    CharacterVoiceProfile,
    Faction,
    Location,
    PlotThread,
    Revelation,
    SceneCard,
    Theme,
    World,
)


def _trim(text: str, n: int) -> str:
    if not text:
        return ""
    text = text.strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


async def build_story_context(
    db: AsyncSession,
    story_id: str,
    *,
    include_chapter_bodies: bool = False,
    max_chapters: int | None = None,
    extra_graph_block: str = "",
) -> str:
    """Return a compact Markdown context block for the story."""
    world = await db.get(World, story_id)
    characters = (
        await db.execute(select(Character).where(Character.story_id == story_id).order_by(Character.created_at))
    ).scalars().all()
    chapters = (
        await db.execute(select(Chapter).where(Chapter.story_id == story_id).order_by(Chapter.number))
    ).scalars().all()
    locations = (
        await db.execute(select(Location).where(Location.story_id == story_id))
    ).scalars().all()
    factions = (
        await db.execute(select(Faction).where(Faction.story_id == story_id))
    ).scalars().all()
    themes = (
        await db.execute(select(Theme).where(Theme.story_id == story_id))
    ).scalars().all()
    threads = (
        await db.execute(select(PlotThread).where(PlotThread.story_id == story_id))
    ).scalars().all()
    scenes = (
        await db.execute(select(SceneCard).where(SceneCard.story_id == story_id))
    ).scalars().all()
    revelations = (
        await db.execute(select(Revelation).where(Revelation.story_id == story_id).order_by(Revelation.created_at))
    ).scalars().all()
    relationships = (
        await db.execute(select(CharacterRelationship).where(CharacterRelationship.story_id == story_id))
    ).scalars().all()
    voice_profiles = (
        await db.execute(select(CharacterVoiceProfile).where(CharacterVoiceProfile.story_id == story_id))
    ).scalars().all()
    char_by_id = {c.id: c.name for c in characters}
    loc_by_id = {loc.id: loc.name for loc in locations}
    chapter_by_id = {ch.id: ch for ch in chapters}
    thread_by_id = {t.id: t.name for t in threads}

    parts: list[str] = []

    parts.append("# WORLD")
    if world:
        parts.append(f"Title: {world.title or '(untitled)'}")
        parts.append(f"Genre: {world.genre or '—'}")
        parts.append(f"Logline: {_trim(world.logline, 400)}")
        if world.time_period:
            parts.append(f"Time period: {world.time_period}")
        if world.setting:
            parts.append(f"Setting: {_trim(world.setting, 600)}")
        if world.rules:
            parts.append("World rules (always respect):")
            for r in world.rules:
                parts.append(f"  • {r}")
        if world.themes:
            parts.append("Themes: " + ", ".join(world.themes))
        if world.lore:
            parts.append(f"Lore: {_trim(world.lore, 800)}")
        if world.seeds:
            parts.append(f"Seeds (foreshadowing): {_trim(world.seeds, 400)}")
    parts.append("")

    if characters:
        parts.append("# CAST")
        for c in characters:
            line = f"- {c.name}"
            bits = []
            if c.role:
                bits.append(c.role)
            if c.status and c.status != "alive":
                bits.append(c.status)
            if bits:
                line += " (" + ", ".join(bits) + ")"
            if c.personality:
                line += f" — {_trim(c.personality, 100)}"
            if c.arc:
                line += f" | arc: {_trim(c.arc, 100)}"
            parts.append(line)
        parts.append("")

    if relationships:
        parts.append("# RELATIONSHIPS")
        for r in relationships:
            src = char_by_id.get(r.source_id, "?")
            dst = char_by_id.get(r.target_id, "?")
            line = f"- {src} → {dst}: {r.type}"
            if r.description:
                line += f" — {_trim(r.description, 120)}"
            parts.append(line)
        parts.append("")

    if locations:
        parts.append("# LOCATIONS")
        for loc in locations:
            parts.append(f"- {loc.name}: {_trim(loc.description, 120)}")
        parts.append("")

    if factions:
        parts.append("# FACTIONS")
        for f in factions:
            parts.append(f"- {f.name}: {_trim(f.description, 120)}")
        parts.append("")

    if themes:
        parts.append("# THEMES")
        parts.append(", ".join(t.name for t in themes))
        parts.append("")

    if threads:
        parts.append("# PLOT THREADS")
        for t in threads:
            parts.append(f"- {t.name} ({t.status}): {_trim(t.description, 160)}")
        parts.append("")

    if chapters:
        parts.append("# CHAPTERS (summaries)")
        for ch in (chapters[-max_chapters:] if max_chapters else chapters):
            head = f"Ch{ch.number}. {ch.title or '(untitled)'}"
            summary = _trim(ch.summary or ch.content[:200], 200)
            parts.append(f"- {head} — {summary}")
            if include_chapter_bodies:
                parts.append(_trim(ch.content, 1500))
        parts.append("")

    if scenes:
        parts.append("# SCENES (stored analysis)")
        ordered_scenes = sorted(
            scenes,
            key=lambda s: (
                chapter_by_id.get(s.chapter_id).number if s.chapter_id in chapter_by_id else 999999,
                s.ordinal,
            ),
        )
        for s in ordered_scenes:
            ch = chapter_by_id.get(s.chapter_id or "")
            label = f"Ch{ch.number}." if ch else "Unassigned."
            head = s.title or s.beat or s.summary[:60] or "Untitled scene"
            bits = []
            if s.time_sort_key is not None:
                bits.append(f"time_key={s.time_sort_key:.2g}")
            if s.time_anchor:
                bits.append(f"time={s.time_anchor}")
            if s.pov_character_id and s.pov_character_id in char_by_id:
                bits.append(f"POV={char_by_id[s.pov_character_id]}")
            if s.location_id and s.location_id in loc_by_id:
                bits.append(f"location={loc_by_id[s.location_id]}")
            if s.plot_thread_ids:
                names = [thread_by_id[tid] for tid in s.plot_thread_ids if tid in thread_by_id]
                if names:
                    bits.append("threads=" + ", ".join(names[:4]))
            line = f"- {label}{s.ordinal} {head}"
            if bits:
                line += " [" + "; ".join(bits) + "]"
            detail = " / ".join(x for x in [s.goal, s.conflict, s.outcome] if x)
            if detail:
                line += f" — {_trim(detail, 220)}"
            parts.append(line)
        parts.append("")

    if revelations:
        parts.append("# REVELATIONS / INFORMATION LEDGER")
        for r in revelations:
            ch = chapter_by_id.get(r.chapter_id or "")
            loc = f"Ch{ch.number}" if ch else "Unassigned"
            knowers = [char_by_id[cid] for cid in (r.characters_who_know or []) if cid in char_by_id]
            who = ", ".join(knowers) if knowers else "unknown characters"
            reader = "reader knows" if r.reader_knows else "reader does not know yet"
            parts.append(f"- {loc}: {_trim(r.description, 180)} ({who}; {reader})")
        parts.append("")

    if voice_profiles:
        parts.append("# CHARACTER VOICE FINGERPRINTS")
        for p in voice_profiles:
            name = char_by_id.get(p.character_id, "Unknown")
            if p.sample_count <= 0:
                continue
            parts.append(
                f"- {name}: samples={p.sample_count}, avg_sentence_words={p.avg_sentence_words}, "
                f"question_rate={p.question_rate}, exclamation_rate={p.exclamation_rate}, "
                f"vocab_variety={p.vocabulary_variety}"
            )
        parts.append("")

    if extra_graph_block:
        parts.append("# GRAPH CONTEXT")
        parts.append(extra_graph_block.strip())
        parts.append("")

    return "\n".join(parts).strip()
