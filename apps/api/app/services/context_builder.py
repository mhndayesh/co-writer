"""Build the structured story context the LLM sees on every call.

Mirror of Story_Forge_Docs.md §5.2: `buildCtx(world, chars, chaps)` —
extended to include locations, factions, themes, and (optionally) a
Graph-RAG slice built from Qdrant + Neo4j (see rag_service).

## Size budget (why this file is shaped the way it is)

Older versions dumped the *entire* story into every prompt. That cost grows
linearly with the manuscript — a 60-chapter novel could spend 15k+ tokens of
context on every polish/extract/companion call, and eventually overflow the
model's window. So sections are now assembled as priority-tagged blocks and
packed under a character budget:

  * A typical story (< ~40 chapters) assembles well under the budget, so every
    section is included **in the original order — output is identical to before.**
  * Only long manuscripts hit the ceiling. Then the lowest-priority sections
    (voice fingerprints, scenes, …) are dropped first, each with a marker, while
    the load-bearing ones (world bible + the full cast roster, which `extract`
    needs to set `is_new` correctly, + the RAG graph slice) are always kept.

Degradation is by *detail*, never by silently dropping the cast.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Chapter,
    Character,
    CharacterIdentity,
    CharacterRelationship,
    CharacterState,
    CharacterVoiceProfile,
    Faction,
    Location,
    PlaceIdentity,
    PlotThread,
    RelationshipMask,
    Revelation,
    SceneCard,
    Theme,
    World,
)

# Soft ceiling on the assembled context, in characters (~4 chars/token, so
# ~7k tokens). Tuned so normal stories never reach it; only long manuscripts do.
CONTEXT_CHAR_BUDGET = 32_000

# Per-section pre-caps on the unbounded list sections, so a 200-chapter novel
# doesn't even build a giant block before the budget pass. Generous enough that
# ordinary stories are untouched; the most *recent* items are kept.
_MAX_CHAPTERS_CTX = 80
_MAX_SCENES_CTX = 160
_MAX_REVELATIONS_CTX = 120

# Section priorities. Higher survives longer when over budget. Sections at or
# above _ALWAYS_KEEP are never dropped (world bible, full cast roster, RAG slice).
_ALWAYS_KEEP = 90
_P_WORLD = 100
_P_CAST = 95
_P_SCENE_FOCUS = 94  # in-scene characters' FULL identity — never dropped (≥ _ALWAYS_KEEP)
_P_GRAPH = 92
_P_THREADS = 80
_P_CHAPTERS = 78
_P_RELATIONSHIPS = 70
_P_THEMES = 60
_P_LOCATIONS = 55
_P_FACTIONS = 55
_P_REVELATIONS = 48
_P_SCENES = 42
# Voice Studio (Narrative Fidelity Engine) — rich identity. All below _ALWAYS_KEEP
# and around _P_VOICE so they degrade by *detail* first; the cast roster is never
# dropped. Masks slightly outrank the rest (they most directly shape dialogue).
_P_MASKS = 36
_P_PLACE = 34
_P_IDENTITY = 30
_P_VOICE = 25


def _trim(text: str, n: int) -> str:
    if not text:
        return ""
    text = text.strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _summarize_layer(blob: dict, keys: list[str], *, each: int = 60, total: int = 200) -> str:
    """Compact a JSON identity layer into one trimmed 'key: value' line. Used to
    fold the rich Voice Studio layers into context without blowing the budget."""
    parts: list[str] = []
    for k in keys:
        v = (blob or {}).get(k)
        if isinstance(v, dict):
            v = "; ".join(f"{kk} {vv}" for kk, vv in v.items() if vv)
        if isinstance(v, list):
            v = ", ".join(str(x) for x in v if x)
        if v:
            parts.append(f"{k.replace('_', ' ')}: {_trim(str(v), each)}")
    return _trim("; ".join(parts), total)


def _full_layer(blob: dict, *, each: int = 200) -> str:
    """Emit EVERY filled key of a layer (not just the budget-picked few). Used for
    scene-focus characters, whose full identity is pinned and never trimmed."""
    parts: list[str] = []
    for k, v in (blob or {}).items():
        if k == "shifts":
            continue  # rendered separately below
        if isinstance(v, list):
            v = ", ".join(str(x) for x in v if x)
        if isinstance(v, dict):
            v = "; ".join(f"{kk} {vv}" for kk, vv in v.items() if vv)
        if v:
            parts.append(f"{k.replace('_', ' ')}: {_trim(str(v), each)}")
    return " | ".join(parts)


# Which keys from each layer are worth spending context budget on (the most
# voice/behavior-defining). Keys are the interview question ids — the one shared
# vocabulary across analyze / interview / editor / context. The full layer stays
# available in the Voice Studio UI and in the pinned SCENE FOCUS section.
_CTX_CORE_KEYS = ["lie", "want", "shame", "value_hierarchy"]
_CTX_BEHAVIOR_KEYS = ["stress_response", "deception", "anger_tell"]
_CTX_VOICE_KEYS = [
    "cadence", "directness", "register", "humor",
    "lexicon", "emotion_shift", "silence", "shifts",
]


def _block_len(block: list[str]) -> int:
    # +1 per line for the newline join, +1 for the blank separator after the block.
    return sum(len(line) + 1 for line in block) + 1


def _pack(sections: list[tuple[int, list[str]]], budget: int) -> str:
    """Join section blocks under `budget`, dropping lowest-priority blocks first.

    For an under-budget story this returns exactly what a naive join would —
    every block, in build order — so existing prompts are unchanged.
    """
    total = sum(_block_len(b) for _, b in sections if b)
    dropped: set[int] = set()
    if total > budget:
        # Drop lowest priority first; ties broken by later position (drop tail).
        order = sorted(
            range(len(sections)),
            key=lambda i: (sections[i][0], i),
        )
        for i in order:
            if total <= budget:
                break
            prio, block = sections[i]
            if not block or prio >= _ALWAYS_KEEP:
                continue
            total -= _block_len(block)
            dropped.add(i)

    parts: list[str] = []
    for i, (_prio, block) in enumerate(sections):
        if not block or i in dropped:
            continue
        parts.extend(block)
        parts.append("")
    return "\n".join(parts).strip()


async def build_story_context(
    db: AsyncSession,
    story_id: str,
    *,
    include_chapter_bodies: bool = False,
    max_chapters: int | None = None,
    extra_graph_block: str = "",
    char_budget: int | None = None,
    include_entity_ids: bool = False,
    scene_character_ids: list[str] | None = None,
    scene_location_id: str | None = None,
) -> str:
    """Return a compact Markdown context block for the story, capped at a budget.

    `include_entity_ids=True` appends each character's stable `[id:…]` to its CAST
    line so the extract call can echo it back and resolve existing characters
    unambiguously (two same-named cast members can't be told apart by name alone).
    Off by default — polish/companion produce prose and don't need the ID noise,
    so their prompts stay unchanged.

    `scene_character_ids` / `scene_location_id` (Voice Studio "scene setup"): when
    the author marks who/where a scene is, those characters' FULL identity (+ masks
    + active state) and that location's place identity are pinned in a high-priority
    `# SCENE FOCUS` section that is never trimmed — so the people actually in the
    scene always get their complete voice, even on huge manuscripts. They're then
    skipped in the general (droppable) identity/place sections to avoid duplication.
    Blank → behaves exactly as before.
    """
    budget = char_budget if char_budget is not None else CONTEXT_CHAR_BUDGET

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
    # Voice Studio (Narrative Fidelity Engine) — rich identity layers.
    identities = (
        await db.execute(select(CharacterIdentity).where(CharacterIdentity.story_id == story_id))
    ).scalars().all()
    masks = (
        await db.execute(select(RelationshipMask).where(RelationshipMask.story_id == story_id))
    ).scalars().all()
    states = (
        await db.execute(
            select(CharacterState).where(
                CharacterState.story_id == story_id, CharacterState.active.is_(True)
            )
        )
    ).scalars().all()
    place_identities = (
        await db.execute(select(PlaceIdentity).where(PlaceIdentity.story_id == story_id))
    ).scalars().all()
    char_by_id = {c.id: c.name for c in characters}
    loc_by_id = {loc.id: loc.name for loc in locations}
    chapter_by_id = {ch.id: ch for ch in chapters}
    thread_by_id = {t.id: t.name for t in threads}
    identity_by_char = {i.character_id: i for i in identities}
    states_by_char: dict[str, list[CharacterState]] = {}
    for st in states:
        states_by_char.setdefault(st.character_id, []).append(st)
    place_by_loc = {p.location_id: p for p in place_identities}
    masks_by_speaker: dict[str, list[RelationshipMask]] = {}
    for mk in masks:
        masks_by_speaker.setdefault(mk.character_id, []).append(mk)

    # Scene focus: characters/location the author marked as present in this scene.
    # Their identity is pinned (never trimmed) and skipped in the general sections.
    focus_char_ids = {cid for cid in (scene_character_ids or []) if cid in char_by_id}
    focus_loc_id = scene_location_id if scene_location_id in loc_by_id else None

    sections: list[tuple[int, list[str]]] = []

    # ── WORLD (always kept) ──────────────────────────────────────────────────
    block: list[str] = ["# WORLD"]
    if world:
        block.append(f"Title: {world.title or '(untitled)'}")
        block.append(f"Genre: {world.genre or '—'}")
        block.append(f"Logline: {_trim(world.logline, 400)}")
        if world.time_period:
            block.append(f"Time period: {world.time_period}")
        if world.setting:
            block.append(f"Setting: {_trim(world.setting, 600)}")
        if world.rules:
            block.append("World rules (always respect):")
            for r in world.rules:
                block.append(f"  • {r}")
        if world.themes:
            block.append("Themes: " + ", ".join(world.themes))
        if world.lore:
            block.append(f"Lore: {_trim(world.lore, 800)}")
        if world.seeds:
            block.append(f"Seeds (foreshadowing): {_trim(world.seeds, 400)}")
    sections.append((_P_WORLD, block))

    # ── CAST (always kept — extract needs the full roster for is_new) ─────────
    if characters:
        block = ["# CAST"]
        if include_entity_ids:
            block.append("(Each entry ends with its [id:…]. To refer to an existing "
                         "character, copy that exact id into the character's character_id field.)")
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
            if include_entity_ids:
                line += f" [id:{c.id}]"
            block.append(line)
        sections.append((_P_CAST, block))

    # ── SCENE FOCUS (in-scene cast's FULL identity — pinned, never trimmed) ────
    if focus_char_ids or focus_loc_id:
        block = ["# SCENE FOCUS (the characters/place in THIS scene — match them exactly)"]
        for c in characters:
            if c.id not in focus_char_ids:
                continue
            ident = identity_by_char.get(c.id)
            block.append(f"## {c.name}" + (f" ({c.role})" if c.role else ""))
            if ident:
                core = _full_layer(ident.core_personality or {})
                beh = _full_layer(ident.behavioral_patterns or {})
                voc = _full_layer(ident.voice_fingerprint or {})
                if core:
                    block.append(f"  core — {core}")
                if beh:
                    block.append(f"  behavior — {beh}")
                if voc:
                    block.append(f"  voice — {voc}")
                shifts = (ident.voice_fingerprint or {}).get("shifts") or {}
                shift_str = "; ".join(f"{k} {v}" for k, v in shifts.items() if v)
                if shift_str:
                    block.append(f"  voice shifts — {shift_str}")
            for mk in masks_by_speaker.get(c.id, []):
                if not mk.speech_style:
                    continue
                audience = char_by_id.get(mk.audience_character_id or "", mk.audience_label or "?")
                line = f"  → speaking to {audience}: {_trim(mk.speech_style, 160)}"
                if mk.tells:
                    line += f" (tells: {_trim(mk.tells, 80)})"
                block.append(line)
            active_states = states_by_char.get(c.id, [])
            if active_states:
                st = "; ".join(_trim(f"{s.label} ({s.detail})" if s.detail else s.label, 80) for s in active_states[:4])
                block.append(f"  current state — {st}")
        if focus_loc_id:
            place = place_by_loc.get(focus_loc_id)
            block.append(f"## Place: {loc_by_id.get(focus_loc_id, '?')}")
            if place:
                if place.atmosphere:
                    block.append(f"  atmosphere — {_trim(place.atmosphere, 200)}")
                sens = ", ".join(f"{k} {v}" for k, v in (place.sensory_palette or {}).items() if v)
                if sens:
                    block.append(f"  senses — {_trim(sens, 200)}")
                if place.symbolic_motif:
                    block.append(f"  motif — {_trim(place.symbolic_motif, 100)}")
        if len(block) > 1:
            sections.append((_P_SCENE_FOCUS, block))

    # ── CHARACTER IDENTITY (Voice Studio — droppable, degrades by detail) ──────
    # Scene-focus characters are pinned above, so skip them here to avoid duplication.
    if identities:
        block = ["# CHARACTER IDENTITY (voice & behavior)"]
        for c in characters:
            if c.id in focus_char_ids:
                continue
            ident = identity_by_char.get(c.id)
            if ident is None:
                continue
            entry_lines: list[str] = []
            core = _summarize_layer(ident.core_personality or {}, _CTX_CORE_KEYS)
            beh = _summarize_layer(ident.behavioral_patterns or {}, _CTX_BEHAVIOR_KEYS)
            voc = _summarize_layer(ident.voice_fingerprint or {}, _CTX_VOICE_KEYS, total=240)
            if core:
                entry_lines.append(f"  core — {core}")
            if beh:
                entry_lines.append(f"  behavior — {beh}")
            if voc:
                entry_lines.append(f"  voice — {voc}")
            active_states = states_by_char.get(c.id, [])
            if active_states:
                st = "; ".join(_trim(f"{s.label} ({s.detail})" if s.detail else s.label, 60) for s in active_states[:3])
                entry_lines.append(f"  current state — {st}")
            if entry_lines:
                block.append(f"- {c.name}:")
                block.extend(entry_lines)
        if len(block) > 1:
            sections.append((_P_IDENTITY, block))

    # ── RELATIONSHIP MASKS (per-audience speech style) ────────────────────────
    if masks:
        block = ["# RELATIONSHIP MASKS (how each speaks to different audiences)"]
        for m in masks:
            speaker = char_by_id.get(m.character_id, "?")
            audience = char_by_id.get(m.audience_character_id or "", m.audience_label or "?")
            style = _trim(m.speech_style, 120)
            if not style:
                continue
            line = f"- {speaker} → {audience}: {style}"
            if m.tells:
                line += f" (tells: {_trim(m.tells, 60)})"
            block.append(line)
        if len(block) > 1:
            sections.append((_P_MASKS, block))

    if relationships:
        block = ["# RELATIONSHIPS"]
        for r in relationships:
            src = char_by_id.get(r.source_id, "?")
            dst = char_by_id.get(r.target_id, "?")
            line = f"- {src} → {dst}: {r.type}"
            if r.description:
                line += f" — {_trim(r.description, 120)}"
            block.append(line)
        sections.append((_P_RELATIONSHIPS, block))

    if locations:
        block = ["# LOCATIONS"]
        for loc in locations:
            block.append(f"- {loc.name}: {_trim(loc.description, 120)}")
        sections.append((_P_LOCATIONS, block))

    # ── PLACE IDENTITY (Voice Studio — atmosphere/sensory; droppable) ─────────
    # The scene-focus location is pinned above; skip it here to avoid duplication.
    if place_identities:
        block = ["# PLACE IDENTITY (atmosphere & sensory palette)"]
        for loc in locations:
            if loc.id == focus_loc_id:
                continue
            place = place_by_loc.get(loc.id)
            if place is None:
                continue
            bits = []
            if place.atmosphere:
                bits.append(f"atmosphere: {_trim(place.atmosphere, 100)}")
            sensory = place.sensory_palette or {}
            sens = ", ".join(f"{k} {v}" for k, v in sensory.items() if v)
            if sens:
                bits.append(f"senses: {_trim(sens, 120)}")
            if place.symbolic_motif:
                bits.append(f"motif: {_trim(place.symbolic_motif, 60)}")
            if bits:
                block.append(f"- {loc.name}: " + "; ".join(bits))
        if len(block) > 1:
            sections.append((_P_PLACE, block))

    if factions:
        block = ["# FACTIONS"]
        for f in factions:
            block.append(f"- {f.name}: {_trim(f.description, 120)}")
        sections.append((_P_FACTIONS, block))

    if themes:
        block = ["# THEMES", ", ".join(t.name for t in themes)]
        sections.append((_P_THEMES, block))

    if threads:
        block = ["# PLOT THREADS"]
        for t in threads:
            block.append(f"- {t.name} ({t.status}): {_trim(t.description, 160)}")
        sections.append((_P_THREADS, block))

    if chapters:
        # Keep the most recent chapters when there are very many. `max_chapters`
        # (explicit caller intent) wins; otherwise apply the implicit ceiling.
        limit = max_chapters if max_chapters is not None else _MAX_CHAPTERS_CTX
        shown = chapters[-limit:] if limit and len(chapters) > limit else chapters
        omitted = len(chapters) - len(shown)
        block = ["# CHAPTERS (summaries)"]
        if omitted > 0:
            block.append(f"(… {omitted} earlier chapter(s) omitted; most recent shown)")
        for ch in shown:
            head = f"Ch{ch.number}. {ch.title or '(untitled)'}"
            summary = _trim(ch.summary or ch.content[:200], 200)
            block.append(f"- {head} — {summary}")
            if include_chapter_bodies:
                block.append(_trim(ch.content, 1500))
        sections.append((_P_CHAPTERS, block))

    if scenes:
        ordered_scenes = sorted(
            scenes,
            key=lambda s: (
                chapter_by_id.get(s.chapter_id).number if s.chapter_id in chapter_by_id else 999999,
                s.ordinal,
            ),
        )
        scene_omitted = 0
        if len(ordered_scenes) > _MAX_SCENES_CTX:
            scene_omitted = len(ordered_scenes) - _MAX_SCENES_CTX
            ordered_scenes = ordered_scenes[-_MAX_SCENES_CTX:]
        block = ["# SCENES (stored analysis)"]
        if scene_omitted > 0:
            block.append(f"(… {scene_omitted} earlier scene card(s) omitted; most recent shown)")
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
            block.append(line)
        sections.append((_P_SCENES, block))

    if revelations:
        shown_rev = revelations
        rev_omitted = 0
        if len(revelations) > _MAX_REVELATIONS_CTX:
            rev_omitted = len(revelations) - _MAX_REVELATIONS_CTX
            shown_rev = revelations[-_MAX_REVELATIONS_CTX:]
        block = ["# REVELATIONS / INFORMATION LEDGER"]
        if rev_omitted > 0:
            block.append(f"(… {rev_omitted} earlier revelation(s) omitted; most recent shown)")
        for r in shown_rev:
            ch = chapter_by_id.get(r.chapter_id or "")
            loc = f"Ch{ch.number}" if ch else "Unassigned"
            knowers = [char_by_id[cid] for cid in (r.characters_who_know or []) if cid in char_by_id]
            who = ", ".join(knowers) if knowers else "unknown characters"
            reader = "reader knows" if r.reader_knows else "reader does not know yet"
            block.append(f"- {loc}: {_trim(r.description, 180)} ({who}; {reader})")
        sections.append((_P_REVELATIONS, block))

    if voice_profiles:
        block = ["# CHARACTER VOICE FINGERPRINTS"]
        for p in voice_profiles:
            name = char_by_id.get(p.character_id, "Unknown")
            if p.sample_count <= 0:
                continue
            block.append(
                f"- {name}: samples={p.sample_count}, avg_sentence_words={p.avg_sentence_words}, "
                f"question_rate={p.question_rate}, exclamation_rate={p.exclamation_rate}, "
                f"vocab_variety={p.vocabulary_variety}"
            )
        # Only add if it has real content beyond the heading.
        if len(block) > 1:
            sections.append((_P_VOICE, block))

    if extra_graph_block:
        block = ["# GRAPH CONTEXT", extra_graph_block.strip()]
        sections.append((_P_GRAPH, block))

    return _pack(sections, budget)
