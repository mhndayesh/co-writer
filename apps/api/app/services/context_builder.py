"""Build the structured story context the LLM sees on every call.

Mirror of Story_Forge_Docs.md §5.2: `buildCtx(world, chars, chaps)` —
extended to include locations, factions, themes, and (optionally) a
Graph-RAG slice built from Qdrant + Neo4j (see rag_service).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chapter, Character, Faction, Location, Theme, World


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
    max_chapters: int = 20,
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

    if chapters:
        parts.append("# CHAPTERS (summaries)")
        for ch in chapters[-max_chapters:]:
            head = f"Ch{ch.number}. {ch.title or '(untitled)'}"
            summary = _trim(ch.summary or ch.content[:200], 200)
            parts.append(f"- {head} — {summary}")
            if include_chapter_bodies:
                parts.append(_trim(ch.content, 1500))
        parts.append("")

    if extra_graph_block:
        parts.append("# GRAPH CONTEXT")
        parts.append(extra_graph_block.strip())
        parts.append("")

    return "\n".join(parts).strip()
