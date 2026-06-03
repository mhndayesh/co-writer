"""Character Voice Studio — the writing-process surfaces (Part 2 of the spec):

  - Place Identity build (Part 1C)
  - Narrative Observer  : line-level critique of a draft (evolves the Story Check
                          dialogue pass), with "mark intentional" memory so flagged
                          deviations stop reappearing.
  - Dialogue Writer     : rewrite a draft in character.
  - Post-scene evolve   : propose identity deltas after a scene; the author chooses
                          temporary / recurring / permanent / not-saved.
  - Voice comparison    : same situation, side-by-side responses.

All author text is fenced (reusing the registered author_draft/author_text tags)
and SECURITY_CLAUSE is appended. Every JSON parse tolerates the fallback provider
returning non-JSON (parse_json(...) or {} + isinstance guards), like flow_service.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound
from app.core.prompt_safety import SECURITY_CLAUSE, fence
from app.db.models import (
    Character,
    CharacterState,
    Location,
    PlaceIdentity,
    User,
    VoiceException,
)
from app.services import identity_service, llm_service
from app.services.context_builder import build_story_context
from app.services.identity_questions import PLACE_FIELD_MAP

_STRICTNESS_GUIDANCE = {
    "light": "Light touch: only flag clear, high-confidence problems. Skip nitpicks.",
    "balanced": "Balanced: flag real voice/behavior/atmosphere issues; skip trivialities.",
    "strict": "Strict character fidelity: hold every line to the character's identity; "
              "flag even subtle drift.",
}
_STRICTNESS_MIN_CONF = {"light": 0.7, "balanced": 0.45, "strict": 0.0}


def line_fingerprint(character_id: str | None, line: str, note_kind: str) -> str:
    """Stable hash over (character, normalized line, note kind). Normalizing on
    whitespace+case means trivial edits don't resurrect the flag, but a real
    rewrite of the line does (its text changes)."""
    norm = re.sub(r"\s+", " ", (line or "").strip().lower())
    raw = f"{character_id or ''}|{norm}|{note_kind or ''}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:64]


# ── Place Identity (Part 1C) ────────────────────────────────────────────────────

async def _require_location(db: AsyncSession, story_id: str, location_id: str) -> Location:
    loc = await db.get(Location, location_id)
    if loc is None or loc.story_id != story_id:
        raise NotFound("Location not found")
    return loc


async def get_place_identity(db: AsyncSession, story_id: str, location_id: str) -> PlaceIdentity:
    await _require_location(db, story_id, location_id)
    row = (
        await db.execute(
            select(PlaceIdentity).where(
                PlaceIdentity.story_id == story_id, PlaceIdentity.location_id == location_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = PlaceIdentity(story_id=story_id, location_id=location_id)
        db.add(row)
        await db.flush()
    return row


async def patch_place_identity(db: AsyncSession, story_id: str, location_id: str, patch: dict) -> PlaceIdentity:
    place = await get_place_identity(db, story_id, location_id)
    for field, value in patch.items():
        if value is not None and hasattr(place, field):
            setattr(place, field, value)
    place.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return place


PLACE_SYNTH_SYSTEM = """You are a setting designer. The author answered a short
interview about a place. Turn it into a vivid, usable place profile.

Return ONLY a JSON object:
{
  "purpose": "", "atmosphere": "",
  "sensory_palette": {"sound": "", "smell": "", "lighting": "", "temperature": "", "textures": ""},
  "visual_anchors": [], "spatial_layout": "", "controls_space": "",
  "social_rules": "", "normal_behavior": "", "variations": {"time": "", "weather": "", "phase": ""},
  "symbolic_motif": ""
}
Only fill what the answers support; leave the rest empty. Keep it concrete and sensory."""


async def build_place(db: AsyncSession, user: User, story_id: str, location_id: str, answers: dict) -> PlaceIdentity:
    loc = await _require_location(db, story_id, location_id)
    answer_lines = "\n".join(f"- {k}: {v}" for k, v in (answers or {}).items() if v)
    user_msg = f"PLACE: {loc.name}\n\nANSWERS:\n{fence('author_text', answer_lines)}"
    resp, _fb = await llm_service.run(
        db, user, page="voice.place", system=PLACE_SYNTH_SYSTEM + "\n\n" + SECURITY_CLAUSE,
        user_msg=user_msg, json_mode=True, temperature=0.4, max_tokens=2500, story_id=story_id,
    )
    parsed = llm_service.parse_json(resp.text)
    place = await get_place_identity(db, story_id, location_id)
    if isinstance(parsed, dict) and parsed:
        for field in ("purpose", "atmosphere", "spatial_layout", "controls_space",
                      "social_rules", "normal_behavior", "symbolic_motif"):
            if parsed.get(field):
                setattr(place, field, str(parsed[field]))
        if isinstance(parsed.get("sensory_palette"), dict):
            place.sensory_palette = {**(place.sensory_palette or {}), **parsed["sensory_palette"]}
        if isinstance(parsed.get("variations"), dict):
            place.variations = {**(place.variations or {}), **parsed["variations"]}
        if isinstance(parsed.get("visual_anchors"), list):
            place.visual_anchors = [str(x) for x in parsed["visual_anchors"] if x]
    else:
        # Fallback: map raw answers onto fields deterministically so work isn't lost.
        for qid, field in PLACE_FIELD_MAP.items():
            if answers.get(qid) and not getattr(place, field):
                setattr(place, field, str(answers[qid]))
        sensory = dict(place.sensory_palette or {})
        for s in ("sound", "smell", "lighting"):
            if answers.get(s):
                sensory[s] = str(answers[s])
        place.sensory_palette = sensory
    place.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return place


# ── Narrative Observer ──────────────────────────────────────────────────────────

OBSERVER_SYSTEM = """You are a narrative fidelity editor. You receive STORY CONTEXT
(world, cast identity, voice fingerprints, relationship masks, current states, place
identity) and a DRAFT scene. Critique the draft line by line for how it FEELS — not
for plot/canon (a separate Story Check handles that).

Flag, with each note pointing to an EXACT sentence copied verbatim from the draft:
- dialogue that doesn't sound like the character (vs their voice fingerprint)
- vocabulary too formal or too casual for them
- an emotional reaction that feels wrong
- an action that contradicts their established habits
- narration that ignores the place's identity / atmosphere
- a missed opportunity for sensory atmosphere
- repetitive prose
- two characters sounding too similar
- continuity of *behavior* (acting against their current state)

Return ONLY a JSON object:
{
  "notes": [
    {"line": "<exact sentence from the draft>",
     "category": "voice_mismatch|register|wrong_emotion|contradicts_habit|ignores_place|missed_atmosphere|repetitive|too_similar|behavior_continuity",
     "severity": "high|medium|low",
     "confidence": 0.0-1.0,
     "message": "<why it's off, grounded in the character's identity>",
     "suggestion": "<a concrete replacement line or fix>",
     "character": "<name of the character involved, if any>"}
  ]
}
Be specific and sparing — quality over quantity. Quote lines verbatim so they can be located."""


async def observe(
    db: AsyncSession, user: User, story_id: str, draft: str, strictness: str, chapter_id: str | None
) -> dict:
    ctx = await build_story_context(db, story_id)
    guidance = _STRICTNESS_GUIDANCE.get(strictness, _STRICTNESS_GUIDANCE["balanced"])
    user_msg = (
        "STORY CONTEXT (reference only):\n"
        f"{fence('story_context', ctx)}\n\n"
        f"STRICTNESS: {guidance}\n\n"
        "DRAFT TO CRITIQUE:\n"
        f"{fence('author_draft', draft)}"
    )
    resp, fb = await llm_service.run(
        db, user, page="voice.observe", system=OBSERVER_SYSTEM + "\n\n" + SECURITY_CLAUSE,
        user_msg=user_msg, json_mode=True, temperature=0.3, max_tokens=4000, story_id=story_id,
    )
    parsed = llm_service.parse_json(resp.text) or {}
    raw_notes = parsed.get("notes") if isinstance(parsed, dict) else None

    # Character name → id for fingerprinting / profile updates.
    characters = (
        await db.execute(select(Character).where(Character.story_id == story_id))
    ).scalars().all()
    name_to_id = {c.name.lower(): c.id for c in characters}

    # Already-marked-intentional fingerprints for this story.
    exceptions = (
        await db.execute(select(VoiceException.fingerprint).where(VoiceException.story_id == story_id))
    ).scalars().all()
    silenced = set(exceptions)
    min_conf = _STRICTNESS_MIN_CONF.get(strictness, 0.45)

    notes = []
    for n in (raw_notes or []):
        if not isinstance(n, dict):
            continue
        try:
            conf = float(n.get("confidence", 0.5))
        except (TypeError, ValueError):
            conf = 0.5
        if conf < min_conf:
            continue
        cname = str(n.get("character", "") or "")
        cid = name_to_id.get(cname.lower())
        category = str(n.get("category", ""))[:64]
        line = str(n.get("line", ""))
        fp = line_fingerprint(cid, line, category)
        if fp in silenced:
            continue  # author marked this intentional — don't re-flag
        notes.append({
            "line": line,
            "category": category,
            "severity": str(n.get("severity", "low")),
            "confidence": max(0.0, min(1.0, conf)),
            "message": str(n.get("message", "")),
            "suggestion": str(n.get("suggestion", "")),
            "character": cname,
            "character_id": cid,
            "fingerprint": fp,
        })
    return {"notes": notes, "fallback": fb}


async def mark_intentional(db: AsyncSession, story_id: str, payload: dict) -> str:
    """Persist a deliberate deviation so the Observer stops re-flagging it."""
    cid = payload.get("character_id") or None
    note_kind = payload.get("note_kind", "")
    line = payload.get("line", "")
    fp = line_fingerprint(cid, line, note_kind)
    existing = (
        await db.execute(
            select(VoiceException).where(
                VoiceException.story_id == story_id, VoiceException.fingerprint == fp
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = VoiceException(
            story_id=story_id, chapter_id=payload.get("chapter_id") or None,
            character_id=cid, fingerprint=fp, line_excerpt=line[:2000],
            note_kind=note_kind, reason=payload.get("reason", ""),
        )
        db.add(existing)
        await db.flush()
    return existing.id


# ── Dialogue Writer (rewrite) ───────────────────────────────────────────────────

REWRITE_SYSTEM = """You are a Dialogue Writer. Rewrite the author's draft so every
character sounds exactly like themselves — consult their voice fingerprint, the
relationship mask for who they're speaking to, and their current state. Honor the
place's atmosphere in the narration. Keep the plot, facts and beats unchanged.

Return ONLY the rewritten prose — no headers, no commentary."""


async def rewrite(db: AsyncSession, user: User, story_id: str, payload: dict) -> dict:
    ctx = await build_story_context(db, story_id)
    draft = payload.get("draft", "")
    instruction = payload.get("instruction", "")
    objective = payload.get("objective", "")
    strictness = payload.get("strictness", "balanced")
    guidance = _STRICTNESS_GUIDANCE.get(strictness, _STRICTNESS_GUIDANCE["balanced"])
    parts = [
        "STORY CONTEXT (reference only):",
        fence("story_context", ctx),
        f"\nEDITING MODE: {guidance}",
    ]
    if objective:
        parts.append(f"SCENE OBJECTIVE: {objective}")
    if instruction:
        parts.append("AUTHOR INSTRUCTION:\n" + fence("author_instruction", instruction))
    if draft:
        parts.append("DRAFT TO REWRITE:\n" + fence("author_draft", draft))
    resp, fb = await llm_service.run(
        db, user, page="voice.rewrite", system=REWRITE_SYSTEM + "\n\n" + SECURITY_CLAUSE,
        user_msg="\n\n".join(parts), temperature=0.7, max_tokens=8000, story_id=story_id,
    )
    return {"rewritten": resp.text.strip(), "fallback": fb}


async def update_profile_from_note(db: AsyncSession, story_id: str, payload: dict) -> object:
    """"Update character profile" correction button — fold a note into a layer."""
    return await identity_service.patch_layer(
        db, story_id, payload["character_id"], payload["layer"],
        {**(await _layer_blob(db, story_id, payload["character_id"], payload["layer"])),
         payload["field"]: payload.get("value", "")},
    )


async def _layer_blob(db: AsyncSession, story_id: str, character_id: str, layer: str) -> dict:
    identity = await identity_service.get_identity(db, story_id, character_id)
    return dict(getattr(identity, identity_service.LAYER_COLUMNS.get(layer, "core_personality")) or {})


# ── Post-scene evolve ───────────────────────────────────────────────────────────

EVOLVE_SYSTEM = """You are a continuity-of-character analyst. Given the cast and a
just-approved scene, propose what this scene REVEALS or CHANGES about the characters
— so the author can decide what becomes canon. Do not commit anything.

Return ONLY a JSON object:
{
  "suggestions": [
    {"type": "new_phrase|revealed_fear|relationship_change|emotional_shift|new_stress_behavior|place_alteration|intentional_development",
     "character": "<name, if applicable>",
     "summary": "<what changed/was revealed>",
     "suggested_save_as": "temporary|recurring|permanent|not_saved",
     "excerpt": "<short quote from the scene>"}
  ]
}
A one-off reaction should be 'temporary'; a pattern that recurs should be 'recurring';
a lasting identity change should be 'permanent'. Be conservative — don't pollute the
profile with noise."""


async def evolve_suggestions(db: AsyncSession, user: User, story_id: str, text: str, chapter_id: str | None) -> dict:
    ctx = await build_story_context(db, story_id)
    user_msg = (
        "STORY CONTEXT (reference only):\n"
        f"{fence('story_context', ctx)}\n\n"
        "JUST-APPROVED SCENE:\n"
        f"{fence('author_text', text)}"
    )
    resp, fb = await llm_service.run(
        db, user, page="voice.evolve", system=EVOLVE_SYSTEM + "\n\n" + SECURITY_CLAUSE,
        user_msg=user_msg, json_mode=True, temperature=0.3, max_tokens=3000, story_id=story_id,
    )
    parsed = llm_service.parse_json(resp.text) or {}
    characters = (
        await db.execute(select(Character).where(Character.story_id == story_id))
    ).scalars().all()
    name_to_id = {c.name.lower(): c.id for c in characters}
    out = []
    for s in (parsed.get("suggestions") if isinstance(parsed, dict) else []) or []:
        if not isinstance(s, dict):
            continue
        cname = str(s.get("character", "") or "")
        out.append({
            "type": str(s.get("type", "")),
            "character": cname,
            "character_id": name_to_id.get(cname.lower()),
            "summary": str(s.get("summary", "")),
            "suggested_save_as": str(s.get("suggested_save_as", "temporary")),
            "excerpt": str(s.get("excerpt", "")),
        })
    return {"suggestions": out, "fallback": fb}


async def apply_evolution(db: AsyncSession, story_id: str, decisions: list[dict]) -> int:
    """Commit each evolve decision per its save-as class. Prevents profile pollution
    by keeping one-offs as temporary states and only promoting 'permanent' to layers."""
    applied = 0
    for d in decisions:
        save_as = d.get("save_as", "not_saved")
        cid = d.get("character_id")
        summary = d.get("summary", "")
        if save_as == "not_saved" or not cid or not summary:
            continue
        if save_as in ("temporary", "recurring"):
            db.add(CharacterState(
                story_id=story_id, character_id=cid, label=d.get("type", "change")[:120],
                detail=summary, kind=save_as, active=(save_as == "recurring"),
            ))
            applied += 1
        elif save_as == "permanent":
            identity = await identity_service.get_identity(db, story_id, cid)
            notes = dict(identity.core_personality or {})
            prior = notes.get("evolution_notes", "")
            notes["evolution_notes"] = (prior + " | " + summary).strip(" |") if prior else summary
            identity.core_personality = notes
            identity.updated_at = datetime.now(timezone.utc)
            await identity_service._record_version(db, story_id, cid, "arc", {"summary": summary}, note="evolve")
            applied += 1
    await db.flush()
    return applied


# ── Voice comparison ────────────────────────────────────────────────────────────

COMPARE_SYSTEM = """You are a casting director testing whether characters feel
distinct. Given several characters' identities and ONE situation, write each
character's brief in-character response (a line or two of dialogue + a beat of action).

Return ONLY a JSON object:
{"entries": [{"character": "<name>", "response": "<their short response>"}]}
Make the voices clearly different from one another. Keep each response short."""


async def compare_voices(db: AsyncSession, user: User, story_id: str, character_ids: list[str], situation: str) -> dict:
    characters = (
        await db.execute(select(Character).where(Character.story_id == story_id))
    ).scalars().all()
    by_id = {c.id: c for c in characters}
    picked = [by_id[cid] for cid in character_ids if cid in by_id]
    if len(picked) < 2:
        raise NotFound("Pick at least two characters in this story")
    ctx = await build_story_context(db, story_id)
    names = ", ".join(c.name for c in picked)
    user_msg = (
        "STORY CONTEXT (reference only):\n"
        f"{fence('story_context', ctx)}\n\n"
        f"CHARACTERS TO COMPARE: {names}\n\n"
        "SITUATION:\n"
        f"{fence('author_text', situation)}"
    )
    resp, fb = await llm_service.run(
        db, user, page="voice.compare", system=COMPARE_SYSTEM + "\n\n" + SECURITY_CLAUSE,
        user_msg=user_msg, json_mode=True, temperature=0.8, max_tokens=3000, story_id=story_id,
    )
    parsed = llm_service.parse_json(resp.text) or {}
    name_to_id = {c.name.lower(): c.id for c in picked}
    entries = []
    for e in (parsed.get("entries") if isinstance(parsed, dict) else []) or []:
        if not isinstance(e, dict):
            continue
        cname = str(e.get("character", ""))
        entries.append({
            "character": cname,
            "character_id": name_to_id.get(cname.lower(), ""),
            "response": str(e.get("response", "")),
        })
    # Fallback: ensure every picked character has at least an entry shell.
    if not entries:
        entries = [{"character": c.name, "character_id": c.id, "response": resp.text.strip()[:400]} for c in picked]
    return {"entries": entries, "fallback": fb}
