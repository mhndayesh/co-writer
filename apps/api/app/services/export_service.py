"""Export a story to Markdown, plain text, DOCX, or a JSON bundle.

The JSON bundle shape matches Story Forge backup format so it round-trips.
"""
from __future__ import annotations

import io
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chapter, Character, Story, World


async def story_to_markdown(db: AsyncSession, story_id: str) -> str:
    story = await db.get(Story, story_id)
    world = await db.get(World, story_id)
    chapters = (await db.execute(select(Chapter).where(Chapter.story_id == story_id).order_by(Chapter.number))).scalars().all()
    characters = (await db.execute(select(Character).where(Character.story_id == story_id))).scalars().all()

    lines: list[str] = []
    lines.append(f"# {story.title or 'Untitled'}")
    if world and world.genre:
        lines.append(f"_{world.genre}_")
    lines.append("")
    if world and world.logline:
        lines.append(f"> {world.logline}")
        lines.append("")
    if characters:
        lines.append("## Cast")
        for c in characters:
            lines.append(f"- **{c.name}** — {c.role or 'unknown role'}")
        lines.append("")
    for ch in chapters:
        lines.append(f"## Chapter {ch.number}. {ch.title or 'Untitled'}")
        if ch.summary:
            lines.append(f"*{ch.summary}*")
            lines.append("")
        lines.append(ch.content or "")
        lines.append("")
    return "\n".join(lines)


async def story_to_bundle(db: AsyncSession, story_id: str) -> dict[str, Any]:
    """Story Forge-compatible JSON bundle."""
    from app.services import version_service

    v = await version_service.snapshot(db, story_id, note="export bundle")
    await db.commit()
    return {"app": "GInkNovelStudio", "version": 1, "story_id": story_id, "snapshot": v.snapshot}


async def story_to_docx_bytes(db: AsyncSession, story_id: str) -> bytes:
    from docx import Document

    md = await story_to_markdown(db, story_id)
    doc = Document()
    for line in md.split("\n"):
        if line.startswith("# "):
            doc.add_heading(line[2:], level=1)
        elif line.startswith("## "):
            doc.add_heading(line[3:], level=2)
        elif line.startswith("> "):
            p = doc.add_paragraph(line[2:])
            p.style = "Intense Quote"
        elif line.startswith("- "):
            doc.add_paragraph(line[2:], style="List Bullet")
        elif line.startswith("*") and line.endswith("*") and len(line) > 2:
            p = doc.add_paragraph()
            run = p.add_run(line.strip("*"))
            run.italic = True
        elif line.strip():
            doc.add_paragraph(line)
        else:
            doc.add_paragraph("")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


async def import_bundle(db: AsyncSession, user_id: str, bundle: dict) -> str:
    """Import a Story Forge / G-Ink bundle and return the new story id."""
    snap = bundle.get("snapshot") or bundle
    world = snap.get("world", {}) or {}
    chars = snap.get("chars", []) or []
    chaps = snap.get("chaps", []) or []
    locs = snap.get("locations", []) or []
    facs = snap.get("factions", []) or []

    story = Story(
        user_id=user_id,
        title=world.get("title") or "Imported Story",
        genre=world.get("genre") or "",
    )
    db.add(story)
    await db.flush()

    db.add(World(
        story_id=story.id,
        title=world.get("title", ""),
        genre=world.get("genre", ""),
        logline=world.get("logline", ""),
        time_period=world.get("time_period", world.get("timePeriod", "")),
        setting=world.get("setting", ""),
        rules=list(world.get("rules") or []),
        themes=list(world.get("themes") or []),
        lore=world.get("lore", ""),
        seeds=world.get("seeds", ""),
    ))

    id_map: dict[str, str] = {}
    for c in chars:
        new_char = Character(
            story_id=story.id,
            name=c.get("name", "Unknown"),
            role=c.get("role", ""),
            icon=c.get("icon", ""),
            age=c.get("age", ""),
            appearance=c.get("appearance", ""),
            personality=c.get("personality", ""),
            backstory=c.get("backstory", ""),
            motivation=c.get("motivation", ""),
            flaw=c.get("flaw", ""),
            arc=c.get("arc", ""),
            status=c.get("status", "alive"),
        )
        db.add(new_char)
        await db.flush()
        if c.get("id"):
            id_map[c["id"]] = new_char.id

    from app.db.models import Location

    loc_id_map: dict[str, str] = {}
    for loc in locs:
        new_loc = Location(
            story_id=story.id,
            name=loc.get("name", ""),
            description=loc.get("description", ""),
            visual=loc.get("visual", ""),
        )
        db.add(new_loc)
        await db.flush()
        if loc.get("id"):
            loc_id_map[loc["id"]] = new_loc.id

    from app.db.models import Faction

    for f in facs:
        db.add(Faction(
            story_id=story.id,
            name=f.get("name", ""),
            description=f.get("description", ""),
            visual_signature=f.get("visual_signature", ""),
        ))

    for ch in chaps:
        new_char_ids = [id_map.get(cid, cid) for cid in (ch.get("characters") or []) if cid in id_map]
        loc = ch.get("location")
        new_loc = loc_id_map.get(loc) if loc else None
        pov = ch.get("pov")
        new_pov = id_map.get(pov) if pov else None
        db.add(Chapter(
            story_id=story.id,
            number=int(ch.get("number") or 1),
            title=ch.get("title", ""),
            content=ch.get("content", ""),
            summary=ch.get("summary", ""),
            pov_character_id=new_pov,
            location_id=new_loc,
            character_ids=new_char_ids,
            seeds=ch.get("seeds") or [],
        ))

    await db.commit()
    return story.id
