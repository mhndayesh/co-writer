"""Flow Writing pipeline — port of story_forge.jsx FlowTab.

Three calls:
  polish(raw, notes)   → polished prose
  extract(polished)    → {title_suggestion, characters, events, themes, locations}
  approve(...)         → commits a new chapter, adds opted-in characters and themes,
                         creates a story_versions snapshot, schedules graph re-projection.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import delete as sa_delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Chapter,
    Character,
    CharacterRelationship,
    Event,
    Faction,
    FlowDraft,
    Location,
    PlotThread,
    PlotThreadSceneLink,
    Revelation,
    SceneCard,
    Story,
    Theme,
    User,
    World,
)
from app.db.schemas import ExtractedScene, FlowApproveRequest, FlowEnhanceResponse, FlowExtractResponse, FlowPolishResponse
from app.services import llm_service
from app.services.context_builder import build_story_context

log = logging.getLogger("gink.flow")


POLISH_SYSTEM = """You are a literary editor. The author writes freely with imagination but limited craft.
Your job: rewrite their raw text as polished, evocative prose that respects the story's world and characters.

The STORY CONTEXT below shows what has already happened — characters, world rules, prior chapters.
The raw text you receive is the NEXT SCENE in this continuing story. Keep it consistent with the
world, the established cast's voices, and what's come before.

Rules:
- Keep the author's intent and key facts intact.
- Match the genre's tone.
- Existing characters should sound like themselves (consult their CAST entries).
- Never invent new characters, locations, or rules — only use what the author wrote or what the WORLD context describes.
- Return ONLY the polished prose, no headers, no commentary.
"""

EXTRACT_SYSTEM = """You are a story analyst. Given a polished scene, extract EVERY piece of
structured information so the writer doesn't have to file anything by hand.

This scene is a CONTINUATION of the story shown in STORY CONTEXT. Treat the existing CAST,
LOCATIONS, FACTIONS, THEMES, and PLOT THREADS as already-known. Only flag truly new entities.
For plot threads that the existing CHAPTERS established, reuse the SAME name and update the
status if this scene resolves or abandons them ("open" → "paid_off" / "abandoned"). Surface
new relationships (or evolutions of old ones) that this scene reveals between named characters.

Return ONLY a single JSON object with EXACTLY these keys:

  title_suggestion: short chapter title (≤ 60 chars)
  summary: 1-2 sentence summary
  pov_suggestion: name of the POV character (must match a name in `characters`)
  location_suggestion: primary location of the scene (must match a name in `locations`)

  characters: every character that appears or is named in the scene
              [{"name": "...", "role": "protagonist|antagonist|ally|mentor|rival|supporting|...",
                "note": "1-line summary of their role IN THIS SCENE",
                "status": "alive|dead|unknown|missing|transformed — ONLY set if status CHANGED in this scene; omit or empty string if unchanged",
                "arc_note": "1-sentence character development observed in this scene — omit or empty if no clear growth/change",
                "is_new": true|false}]
              Mark is_new=true ONLY if absent from the provided CAST.

  relationships: any relationship between two characters that the scene reveals
              [{"source": "<character name>", "target": "<character name>",
                "type": "ally|enemy|lover|rival|family|friend|mentor|student|colleague|...",
                "description": "1-line description"}]
              Both source and target MUST appear in characters[].

  events: every plot-relevant event in the scene
              [{"kind": "encounter|revelation|betrayal|death|decision|conflict|...",
                "description": "1-2 sentences",
                "involved": ["<character name>", ...]}]

  themes: thematic ideas the scene explores
              ["theme phrase 1", "theme phrase 2"]

  locations: every named place that appears in the scene
              [{"name": "...", "description": "1-line description"}]

  factions: organizations, gangs, houses, governments, cults named in the scene
              [{"name": "...", "description": "1-line description"}]

  threads: open subplots / dangling threads to track
              [{"name": "...", "description": "1-line summary", "status": "open|paid_off|abandoned"}]

  scenes: scene-level beat cards in reading order
              [{
                "ordinal": 1,
                "title": "short scene title",
                "beat": "inciting incident|reversal|aftermath|...",
                "summary": "1 sentence",
                "goal": "what the POV/scene wants",
                "conflict": "what blocks the goal",
                "outcome": "what changes by the end",
                "pov": "<character name>",
                "location": "<location name>",
                "characters": ["<character name>", ...],
                "plot_threads": ["<thread name>", ...],
                "time_anchor": "story-time label if stated, e.g. 'three days later'",
                "time_sort_key": "a chronological number (e.g. story-day 1, 2, 3…) — MUST be consistent with existing scene time_key values shown in STORY CONTEXT; null if no clear timeline position",
                "duration_hint": "minutes|hours|overnight|...",
                "sensory_palette": {"sight": 0, "sound": 0, "smell": 0, "taste": 0, "touch": 0},
                "revelations": [
                  {"description": "...", "kind": "revelation|secret|clue|lie|dramatic_irony",
                   "characters_who_know": ["<character name>", ...],
                   "reader_knows": true|false, "notes": "", "confidence": 0.0}
                ],
                "source_excerpt": "short excerpt grounding the card",
                "content": "optional scene card note"
              }]

Rules:
- Use ONLY information present in the POLISHED SCENE. Do not invent.
- Do NOT extract section headers from the STORY CONTEXT (e.g. "WORLD", "CAST", "CHAPTERS")
  as characters or anything else — those are formatting, not story content.
- If a field has nothing, return an empty array (NEVER omit a key).
- Return ONLY the JSON object — no prose, no code fences, no markdown."""


ENHANCE_SYSTEM = """You are a language editor. Your only job is to improve the language quality
of the author's text without touching the story in any way.

Steps:
1. Detect the language of the input text (it may be Arabic, English, or any other language).
2. Fix grammar, punctuation, word choice, sentence flow, and style — in THAT language.
3. Keep EXACTLY the same story content: same events, characters, dialogue meaning, plot beats.
4. Do NOT translate. The output must be in the same language as the input.
5. Do NOT add, remove, or change any story elements. Only the language quality improves.
6. Preserve the author's voice — clean up errors without rewriting their style entirely.

Return ONLY a single JSON object with these keys:
  language: detected language name in English (e.g. "Arabic", "English", "French")
  enhanced: the improved text in the same language as the input
  notes: one or two sentences in English describing what was improved"""


async def enhance(db: AsyncSession, user: User, story_id: str, raw: str) -> FlowEnhanceResponse:
    """Language-enhance the author's own text without changing the story."""
    resp, fb = await llm_service.run(
        db, user, page="flow.enhance", system=ENHANCE_SYSTEM, user_msg=raw,
        json_mode=True, temperature=0.2, story_id=story_id,
    )
    parsed = llm_service.parse_json(resp.text) or {}
    if not isinstance(parsed, dict):
        parsed = {}
    enhanced_text = (parsed.get("enhanced") or "").strip()
    return FlowEnhanceResponse(
        language=(parsed.get("language") or "").strip(),
        enhanced=enhanced_text if enhanced_text else raw,
        notes=(parsed.get("notes") or "").strip(),
        fallback=fb,
    )


def _clean_name_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        name = item.strip()
        key = name.lower()
        if not name or key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def _clean_sensory(value: object) -> dict[str, int]:
    senses = {"sight": 0, "sound": 0, "smell": 0, "taste": 0, "touch": 0}
    if not isinstance(value, dict):
        return senses
    for key in senses:
        raw = value.get(key, 0)
        try:
            n = int(float(raw))
        except Exception:
            n = 0
        senses[key] = max(0, min(100, n))
    return senses


def _clean_sort_key(value: object) -> float | None:
    if value in ("", None):
        return None
    try:
        return float(value)
    except Exception:
        return None


async def polish(db: AsyncSession, user: User, story_id: str, raw: str, notes: str = "") -> FlowPolishResponse:
    ctx = await build_story_context(db, story_id)
    user_msg = f"STORY CONTEXT:\n{ctx}\n\nRAW DRAFT:\n{raw}"
    if notes.strip():
        user_msg += f"\n\nREVISION NOTES FROM AUTHOR:\n{notes}"
    resp, fb = await llm_service.run(
        db, user, page="flow.polish", system=POLISH_SYSTEM, user_msg=user_msg,
        temperature=0.7, max_tokens=None, story_id=story_id,
    )
    return FlowPolishResponse(polished=resp.text.strip(), fallback=fb)


async def extract(db: AsyncSession, user: User, story_id: str, polished: str) -> FlowExtractResponse:
    ctx = await build_story_context(db, story_id)
    user_msg = f"STORY CONTEXT:\n{ctx}\n\nPOLISHED SCENE:\n{polished}"
    resp, fb = await llm_service.run(
        db, user, page="flow.extract", system=EXTRACT_SYSTEM, user_msg=user_msg,
        json_mode=True, temperature=0.2, max_tokens=None, story_id=story_id,
    )
    parsed = llm_service.parse_json(resp.text) or {}
    if not isinstance(parsed, dict):
        parsed = {}

    # Mark which characters are actually new vs already in cast
    existing_chars = (await db.execute(select(Character).where(Character.story_id == story_id))).scalars().all()
    by_name = {c.name.lower(): c for c in existing_chars}
    cleaned_chars = []
    for c in parsed.get("characters", []):
        if not isinstance(c, dict) or not c.get("name"):
            continue
        name = c["name"].strip()
        existing = by_name.get(name.lower())
        raw_status = (c.get("status") or "").strip().lower()
        if raw_status not in ("alive", "dead", "unknown", "missing", "transformed"):
            raw_status = ""
        cleaned_chars.append({
            "name": name,
            "role": c.get("role", "") or "",
            "note": c.get("note", "") or "",
            "status": raw_status,
            "arc_note": (c.get("arc_note") or "").strip(),
            "is_new": existing is None,
            "existing_id": existing.id if existing is not None else None,
        })

    cleaned_events = []
    for e in parsed.get("events", []):
        if not isinstance(e, dict) or not e.get("description"):
            continue
        cleaned_events.append({
            "kind": e.get("kind", "event"),
            "description": e["description"],
            "involved": e.get("involved", []) or [],
        })

    cleaned_rels = []
    char_name_set = {c["name"].lower() for c in cleaned_chars}
    for r in parsed.get("relationships", []):
        if not isinstance(r, dict):
            continue
        src = (r.get("source") or "").strip()
        dst = (r.get("target") or "").strip()
        rtype = (r.get("type") or "").strip()
        if not src or not dst or not rtype or src.lower() == dst.lower():
            continue
        # Only keep relationships between extracted characters
        if src.lower() not in char_name_set or dst.lower() not in char_name_set:
            continue
        cleaned_rels.append({"source": src, "target": dst, "type": rtype, "description": r.get("description", "")})

    cleaned_locations: list[dict] = []
    for loc in parsed.get("locations") or []:
        if isinstance(loc, str):
            cleaned_locations.append({"name": loc.strip(), "description": ""})
        elif isinstance(loc, dict) and loc.get("name"):
            cleaned_locations.append({"name": loc["name"].strip(), "description": loc.get("description", "") or ""})

    cleaned_factions: list[dict] = []
    for f in parsed.get("factions") or []:
        if isinstance(f, str):
            cleaned_factions.append({"name": f.strip(), "description": ""})
        elif isinstance(f, dict) and f.get("name"):
            cleaned_factions.append({"name": f["name"].strip(), "description": f.get("description", "") or ""})

    cleaned_threads: list[dict] = []
    for t in parsed.get("threads") or []:
        if isinstance(t, dict) and t.get("name"):
            status = t.get("status") or "open"
            if status not in ("open", "paid_off", "abandoned"):
                status = "open"
            cleaned_threads.append({"name": t["name"].strip(), "description": t.get("description", "") or "", "status": status})

    cleaned_scenes: list[dict] = []
    for idx, scene in enumerate(parsed.get("scenes") or [], start=1):
        if not isinstance(scene, dict):
            continue
        try:
            ordinal = int(scene.get("ordinal") or idx)
        except Exception:
            ordinal = idx
        revelations: list[dict] = []
        for rev in scene.get("revelations") or []:
            if not isinstance(rev, dict) or not rev.get("description"):
                continue
            try:
                confidence = float(rev.get("confidence", 1.0))
            except Exception:
                confidence = 1.0
            revelations.append({
                "description": str(rev.get("description", "")).strip(),
                "kind": (rev.get("kind") or "revelation").strip() if isinstance(rev.get("kind"), str) else "revelation",
                "characters_who_know": _clean_name_list(rev.get("characters_who_know")),
                "reader_knows": bool(rev.get("reader_knows", False)),
                "notes": rev.get("notes", "") or "",
                "confidence": max(0.0, min(1.0, confidence)),
            })
        cleaned_scenes.append({
            "ordinal": ordinal,
            "title": scene.get("title", "") or "",
            "beat": scene.get("beat", "") or "",
            "summary": scene.get("summary", "") or "",
            "goal": scene.get("goal", "") or "",
            "conflict": scene.get("conflict", "") or "",
            "outcome": scene.get("outcome", "") or "",
            "pov": scene.get("pov", "") or "",
            "location": scene.get("location", "") or "",
            "characters": _clean_name_list(scene.get("characters")),
            "plot_threads": _clean_name_list(scene.get("plot_threads")),
            "time_anchor": scene.get("time_anchor", "") or "",
            "time_sort_key": _clean_sort_key(scene.get("time_sort_key")),
            "duration_hint": scene.get("duration_hint", "") or "",
            "sensory_palette": _clean_sensory(scene.get("sensory_palette")),
            "revelations": revelations,
            "source_excerpt": scene.get("source_excerpt", "") or "",
            "content": scene.get("content", "") or "",
        })

    if not cleaned_scenes and polished.strip():
        cleaned_scenes.append({
            "ordinal": 1,
            "title": parsed.get("title_suggestion", "") or "",
            "beat": "drafted scene",
            "summary": parsed.get("summary", "") or "",
            "goal": "",
            "conflict": "",
            "outcome": "",
            "pov": parsed.get("pov_suggestion", "") or "",
            "location": parsed.get("location_suggestion", "") or "",
            "characters": [c["name"] for c in cleaned_chars],
            "plot_threads": [t["name"] for t in cleaned_threads],
            "time_anchor": "",
            "time_sort_key": None,
            "duration_hint": "",
            "sensory_palette": _clean_sensory({}),
            "revelations": [],
            "source_excerpt": polished[:300],
            "content": "",
        })

    return FlowExtractResponse(
        title_suggestion=parsed.get("title_suggestion", "") or "",
        summary=parsed.get("summary", "") or "",
        pov_suggestion=parsed.get("pov_suggestion", "") or "",
        location_suggestion=parsed.get("location_suggestion", "") or "",
        characters=cleaned_chars,
        events=cleaned_events,
        relationships=cleaned_rels,
        themes=[t for t in (parsed.get("themes") or []) if isinstance(t, str)],
        locations=cleaned_locations,
        factions=cleaned_factions,
        threads=cleaned_threads,
        scenes=cleaned_scenes,
        fallback=fb,
    )


def _resolve_ids_from_names(names: list[str], by_name: dict[str, object]) -> list[str]:
    ids: list[str] = []
    for name in names:
        row = by_name.get(name.strip().lower())
        if row is None:
            continue
        row_id = getattr(row, "id", None)
        if row_id and row_id not in ids:
            ids.append(row_id)
    return ids


def _scene_fallback(payload: FlowApproveRequest) -> ExtractedScene:
    return ExtractedScene(
        ordinal=1,
        title=payload.extracted.title_suggestion or payload.chapter_title,
        beat="drafted scene",
        summary=payload.extracted.summary or payload.chapter_summary,
        pov=payload.extracted.pov_suggestion,
        location=payload.extracted.location_suggestion,
        characters=[c.name for c in payload.extracted.characters],
        plot_threads=[t.name for t in payload.extracted.threads],
        source_excerpt=payload.polished[:300],
    )


async def approve(
    db: AsyncSession,
    user: User,
    story_id: str,
    payload: FlowApproveRequest,
) -> tuple[Chapter, list[str], list[str], int, list[str], list[str], list[str]]:
    """Commit a polished scene to the story.

    File everything the AI found into the right tables so the writer can keep
    writing instead of doing bookkeeping:
      • New chapter (with title, summary, POV, location, characters present)
      • Opted-in new characters (Cast)
      • All new themes (World bible + Themes table)
      • All new locations mentioned (Locations)
      • All extracted events (Events, linked to the chapter)
      • Story snapshot (story_versions)
      • Graph re-projection (Neo4j)
    """
    from app.services import version_service

    story = await db.get(Story, story_id)
    if story is None:
        raise ValueError("story not found")

    # Decide the target chapter:
    #   target_chapter_id  → overwrite that existing chapter
    #   target_chapter_number → create at that specific number (fill a gap)
    #   neither            → append as max(number) + 1
    overwrite_chapter: Chapter | None = None
    if payload.target_chapter_id:
        overwrite_chapter = await db.get(Chapter, payload.target_chapter_id)
        if overwrite_chapter is None or overwrite_chapter.story_id != story_id:
            raise ValueError("target_chapter_id not found in this story")
        next_num = overwrite_chapter.number
    elif payload.target_chapter_number and payload.target_chapter_number > 0:
        # Reject if a chapter already lives at that number
        clash = await db.scalar(select(Chapter.id).where(Chapter.story_id == story_id, Chapter.number == payload.target_chapter_number))
        if clash:
            raise ValueError(f"chapter {payload.target_chapter_number} already exists — pass target_chapter_id to overwrite")
        next_num = payload.target_chapter_number
    else:
        max_num = await db.scalar(select(func.coalesce(func.max(Chapter.number), 0)).where(Chapter.story_id == story_id)) or 0
        next_num = int(max_num) + 1

    # 1. Add ALL new characters automatically (no opt-in — the writer focuses on writing).
    # `include_character_names`, if non-empty, ONLY excludes (an explicit allow-list overrides).
    explicit_allow = {n.strip().lower() for n in payload.include_character_names}
    existing_chars = (await db.execute(select(Character).where(Character.story_id == story_id))).scalars().all()
    existing_by_name = {c.name.lower(): c for c in existing_chars}
    new_char_ids: list[str] = []
    name_to_new_id: dict[str, str] = {}
    for c in payload.extracted.characters:
        if not c.is_new:
            continue
        key = c.name.strip().lower()
        if not key:
            continue
        # If client passed an allow-list, respect it; otherwise auto-add everything new.
        if explicit_allow and key not in explicit_allow:
            continue
        if key in existing_by_name:
            continue
        ch = Character(story_id=story_id, name=c.name.strip(), role=c.role or "", personality=c.note or "")
        db.add(ch)
        await db.flush()
        new_char_ids.append(ch.id)
        name_to_new_id[key] = ch.id
        existing_by_name[key] = ch

    # 1b. Update status / arc for existing characters when the scene changes them.
    for c in payload.extracted.characters:
        if c.is_new:
            continue
        existing_char = existing_by_name.get(c.name.strip().lower())
        if existing_char is None and c.existing_id:
            existing_char = await db.get(Character, c.existing_id)
        if existing_char is None:
            continue
        if c.status and existing_char.status != c.status:
            existing_char.status = c.status
        if c.arc_note:
            existing_char.arc = (
                (existing_char.arc + " · " if existing_char.arc else "") + c.arc_note
            )

    # 2. Weave new themes into the world bible + Themes table
    added_themes: list[str] = []
    if payload.extracted.themes:
        world = await db.get(World, story_id)
        if world is None:
            world = World(story_id=story_id)
            db.add(world)
        current = set((world.themes or []))
        existing_theme_names = {t.lower() for (t,) in await db.execute(select(Theme.name).where(Theme.story_id == story_id))}
        for t in payload.extracted.themes:
            if t and t not in current:
                world.themes = (world.themes or []) + [t]
                current.add(t)
                added_themes.append(t)
            if t and t.lower() not in existing_theme_names:
                db.add(Theme(story_id=story_id, name=t))
                existing_theme_names.add(t.lower())

    # 3. Add new locations (deduped against existing by name)
    existing_loc_rows = (await db.execute(select(Location).where(Location.story_id == story_id))).scalars().all()
    existing_loc_by_name: dict[str, Location] = {
        loc_row.name.lower(): loc_row for loc_row in existing_loc_rows
    }
    chapter_location_id: str | None = None
    for loc in payload.extracted.locations:
        if not loc.name:
            continue
        key = loc.name.strip().lower()
        if key not in existing_loc_by_name:
            new_loc = Location(story_id=story_id, name=loc.name.strip(), description=loc.description or "")
            db.add(new_loc)
            await db.flush()
            existing_loc_by_name[key] = new_loc
        elif loc.description and not existing_loc_by_name[key].description:
            existing_loc_by_name[key].description = loc.description

    # Try to set the chapter's location_id from location_suggestion
    if payload.extracted.location_suggestion:
        sug = payload.extracted.location_suggestion.strip().lower()
        if sug in existing_loc_by_name:
            chapter_location_id = existing_loc_by_name[sug].id
        else:
            new_loc = Location(story_id=story_id, name=payload.extracted.location_suggestion.strip(), description="")
            db.add(new_loc)
            await db.flush()
            existing_loc_by_name[sug] = new_loc
            chapter_location_id = new_loc.id

    # 3b. Add new factions
    existing_fac_rows = (await db.execute(select(Faction).where(Faction.story_id == story_id))).scalars().all()
    existing_fac_names = {f.name.lower() for f in existing_fac_rows}
    for f in payload.extracted.factions:
        if not f.name or f.name.lower() in existing_fac_names:
            continue
        db.add(Faction(story_id=story_id, name=f.name.strip(), description=f.description or ""))
        existing_fac_names.add(f.name.lower())

    # 3c. Add new plot threads OR update existing ones (status evolution).
    # If a thread the AI surfaces matches an existing one by name, we update its
    # status (e.g. "open" → "paid_off") and extend its description. The new
    # chapter gets linked into chapter_ids below, after the chapter is flushed.
    existing_thread_rows = (await db.execute(select(PlotThread).where(PlotThread.story_id == story_id))).scalars().all()
    existing_thread_by_name: dict[str, PlotThread] = {t.name.lower(): t for t in existing_thread_rows}
    for t in payload.extracted.threads:
        if not t.name:
            continue
        key = t.name.lower()
        existing = existing_thread_by_name.get(key)
        if existing is None:
            new_thread = PlotThread(
                story_id=story_id,
                name=t.name.strip(),
                description=t.description or "",
                status=t.status,
                chapter_ids=[],
            )
            db.add(new_thread)
            await db.flush()
            existing_thread_by_name[key] = new_thread
        else:
            # Status evolution: open → paid_off / abandoned is meaningful info from later scenes
            if t.status and t.status != existing.status and t.status in ("open", "paid_off", "abandoned"):
                existing.status = t.status
            # Extend description if the AI offered more detail
            if t.description and t.description not in (existing.description or ""):
                existing.description = (existing.description + " · " if existing.description else "") + t.description

    # 4. Determine character_ids for the chapter (existing referenced + opted-in new)
    referenced_ids: list[str] = []
    name_to_any_id: dict[str, str] = {**{n: c.id for n, c in existing_by_name.items()}, **name_to_new_id}
    for c in payload.extracted.characters:
        if c.existing_id:
            referenced_ids.append(c.existing_id)
        else:
            cid = name_to_any_id.get(c.name.strip().lower())
            if cid and cid not in referenced_ids:
                referenced_ids.append(cid)

    # 5. Resolve POV
    pov_id: str | None = None
    if payload.extracted.pov_suggestion:
        pov_name = payload.extracted.pov_suggestion.strip().lower()
        match_id = name_to_any_id.get(pov_name)
        if match_id:
            pov_id = match_id

    new_title = payload.chapter_title or payload.extracted.title_suggestion or f"Chapter {next_num}"
    new_summary = payload.chapter_summary or payload.extracted.summary
    if overwrite_chapter is not None:
        # Redo: overwrite in place — keeps the chapter id stable so existing
        # links (events, threads, graph nodes) don't break.
        overwrite_chapter.title = new_title
        overwrite_chapter.content = payload.polished
        overwrite_chapter.summary = new_summary
        overwrite_chapter.pov_character_id = pov_id
        overwrite_chapter.location_id = chapter_location_id
        overwrite_chapter.character_ids = referenced_ids
        # Clear stale events that were extracted for the previous content
        await db.execute(sa_delete(Event).where(Event.chapter_id == overwrite_chapter.id))
        await db.execute(sa_delete(PlotThreadSceneLink).where(PlotThreadSceneLink.chapter_id == overwrite_chapter.id))
        await db.execute(sa_delete(Revelation).where(Revelation.chapter_id == overwrite_chapter.id))
        await db.execute(sa_delete(SceneCard).where(SceneCard.chapter_id == overwrite_chapter.id))
        chapter = overwrite_chapter
    else:
        chapter = Chapter(
            story_id=story_id,
            number=next_num,
            title=new_title,
            content=payload.polished,
            summary=new_summary,
            pov_character_id=pov_id,
            location_id=chapter_location_id,
            character_ids=referenced_ids,
            seeds=[],
        )
        db.add(chapter)
    await db.flush()

    # 6. Add extracted events, linked to the new chapter
    for ev in payload.extracted.events:
        if not ev.description:
            continue
        involved_ids: list[str] = []
        for name in (ev.involved or []):
            cid = name_to_any_id.get(name.strip().lower())
            if cid:
                involved_ids.append(cid)
        db.add(Event(
            story_id=story_id,
            chapter_id=chapter.id,
            kind=ev.kind or "event",
            description=ev.description,
            involved=involved_ids,
        ))

    # 7. Add or UPDATE extracted relationships. One row per (source, target)
    # pair — a later chapter that re-describes the same bond updates its type +
    # description instead of stacking a near-duplicate row (mirrors how plot
    # threads evolve). Keyed directionally (source→target), matching how rows
    # are created and how the Characters tab lists each character's own bonds.
    existing_rels = (await db.execute(select(CharacterRelationship).where(CharacterRelationship.story_id == story_id))).scalars().all()
    rel_by_pair: dict[tuple[str, str], CharacterRelationship] = {(r.source_id, r.target_id): r for r in existing_rels}
    for rel in payload.extracted.relationships:
        src_id = name_to_any_id.get(rel.source.strip().lower())
        dst_id = name_to_any_id.get(rel.target.strip().lower())
        if not src_id or not dst_id or src_id == dst_id:
            continue
        existing = rel_by_pair.get((src_id, dst_id))
        if existing is None:
            new_rel = CharacterRelationship(
                story_id=story_id,
                source_id=src_id,
                target_id=dst_id,
                type=rel.type.lower(),
                description=rel.description or "",
            )
            db.add(new_rel)
            rel_by_pair[(src_id, dst_id)] = new_rel
        else:
            # Bond already known — refresh it to the latest description of the pair.
            if rel.type:
                existing.type = rel.type.lower()
            if rel.description:
                existing.description = rel.description

    # 8. Link the new chapter into any plot threads it advances
    if payload.extracted.threads:
        all_threads = (await db.execute(select(PlotThread).where(PlotThread.story_id == story_id))).scalars().all()
        threads_by_name = {t.name.lower(): t for t in all_threads}
        for t in payload.extracted.threads:
            thr = threads_by_name.get(t.name.lower())
            if thr is None:
                continue
            ids = list(thr.chapter_ids or [])
            if chapter.id not in ids:
                ids.append(chapter.id)
                thr.chapter_ids = ids

    # 9. Store scene-level annotations, revelations, and scene-thread links.
    scene_ids: list[str] = []
    revelation_ids: list[str] = []
    thread_scene_link_ids: list[str] = []
    scenes = payload.extracted.scenes or [_scene_fallback(payload)]
    for idx, sc in enumerate(scenes, start=1):
        pov_id = name_to_any_id.get((sc.pov or payload.extracted.pov_suggestion or "").strip().lower())

        loc_id = chapter_location_id
        loc_name = (sc.location or payload.extracted.location_suggestion or "").strip()
        if loc_name:
            loc_key = loc_name.lower()
            loc_row = existing_loc_by_name.get(loc_key)
            if loc_row is None:
                loc_row = Location(story_id=story_id, name=loc_name, description="")
                db.add(loc_row)
                await db.flush()
                existing_loc_by_name[loc_key] = loc_row
            loc_id = loc_row.id

        scene_char_ids = _resolve_ids_from_names(sc.characters, existing_by_name)
        if not scene_char_ids:
            scene_char_ids = list(referenced_ids)

        thread_names = list(sc.plot_threads or [])
        if len(scenes) == 1 and not thread_names:
            thread_names = [t.name for t in payload.extracted.threads]
        scene_thread_ids: list[str] = []
        for name in thread_names:
            key = name.strip().lower()
            if not key:
                continue
            thr = existing_thread_by_name.get(key)
            if thr is None:
                thr = PlotThread(story_id=story_id, name=name.strip(), description="", status="open", chapter_ids=[])
                db.add(thr)
                await db.flush()
                existing_thread_by_name[key] = thr
            if thr.id not in scene_thread_ids:
                scene_thread_ids.append(thr.id)
            ids = list(thr.chapter_ids or [])
            if chapter.id not in ids:
                ids.append(chapter.id)
                thr.chapter_ids = ids

        scene = SceneCard(
            story_id=story_id,
            chapter_id=chapter.id,
            ordinal=sc.ordinal or idx,
            beat=sc.beat or "",
            title=sc.title or "",
            summary=sc.summary or "",
            goal=sc.goal or "",
            conflict=sc.conflict or "",
            outcome=sc.outcome or "",
            pov_character_id=pov_id,
            location_id=loc_id,
            character_ids=scene_char_ids,
            plot_thread_ids=scene_thread_ids,
            time_anchor=sc.time_anchor or "",
            time_sort_key=sc.time_sort_key,
            duration_hint=sc.duration_hint or "",
            sensory_palette=sc.sensory_palette or {},
            source_excerpt=sc.source_excerpt or "",
            content=sc.content or "",
        )
        db.add(scene)
        await db.flush()
        scene_ids.append(scene.id)

        for tid in scene_thread_ids:
            link = PlotThreadSceneLink(
                story_id=story_id,
                thread_id=tid,
                scene_id=scene.id,
                chapter_id=chapter.id,
                status="touch",
                strength=1.0,
                evidence=sc.summary or sc.beat or sc.source_excerpt[:200],
            )
            db.add(link)
            await db.flush()
            thread_scene_link_ids.append(link.id)

        for rev in sc.revelations:
            if not rev.description:
                continue
            knowers = [cid for cid in _resolve_ids_from_names(rev.characters_who_know, existing_by_name) if cid]
            row = Revelation(
                story_id=story_id,
                scene_id=scene.id,
                chapter_id=chapter.id,
                description=rev.description,
                kind=rev.kind or "revelation",
                characters_who_know=knowers,
                reader_knows=rev.reader_knows,
                notes=rev.notes or "",
                confidence=rev.confidence,
            )
            db.add(row)
            await db.flush()
            revelation_ids.append(row.id)

    # 10. Refresh deterministic voice fingerprints now that chapter text exists.
    try:
        from app.services import voice_service

        await voice_service.rebuild_profiles(db, story_id)
    except Exception as e:
        log.debug("voice profile rebuild failed: %s", e)

    # 11. Mark every open draft for this story as approved so the next Flow
    # Writing session starts on a blank slate (the work that was in progress
    # has now been committed as a real chapter).
    open_drafts = (await db.execute(
        select(FlowDraft).where(FlowDraft.story_id == story_id, FlowDraft.approved_at.is_(None))
    )).scalars().all()
    now = datetime.now(timezone.utc)
    for d in open_drafts:
        d.approved_at = now

    # Snapshot the story state
    version = await version_service.snapshot(db, story_id, note=f"flow approve ch{next_num}")

    story.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(chapter)

    # Background graph reprojection (best-effort, no await on failure)
    try:
        from app.services import graph_service

        await graph_service.reproject_story(db, story_id)
    except Exception as e:
        log.warning("graph reprojection failed: %s", e)

    return chapter, new_char_ids, added_themes, version.version_no, scene_ids, revelation_ids, thread_scene_link_ids
