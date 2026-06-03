"""Character Voice Studio — identity CRUD, seeding, and legacy projection.

This is the rich authoring surface for character identity (the 5 layers). The
legacy free-text Character columns (personality/backstory/motivation/flaw/arc)
stay the context-read source for back-compat — so on every structured save we
*compile* the layers down into those columns (`compile_to_legacy`). The Voice
Studio is the only editor; the Characters tab shows the projection read-only.

Layer storage:
  - layers 1-3 (core / behavioral / voice fingerprint) → CharacterIdentity JSON columns
  - layer 4 (relationship masks)                       → RelationshipMask rows
  - layer 5 (current state)                            → CharacterState rows
  - history + arc progression                          → IdentityVersion (append-only)

The deterministic numeric voice stats live in CharacterVoiceProfile (voice_service);
`voice_fingerprint` here holds only the qualitative descriptors. context_builder
merges the two halves at read time.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound
from app.core.prompt_safety import SECURITY_CLAUSE, fence
from app.db.models import (
    Chapter,
    Character,
    CharacterIdentity,
    CharacterState,
    IdentityVersion,
    RelationshipMask,
    User,
)
from app.services import llm_service
from app.services.context_builder import build_story_context

# Keep version history bounded per (character, kind) — same spirit as the
# _MAX_*_CTX caps in context_builder. Snapshots are the changed layer only.
_MAX_VERSIONS_PER_KIND = 50

# Max characters of prose fed into one analyze-writing pass (~32k tokens of sample
# — comfortably more than one long chapter). The story context + JSON response sit
# alongside this within the model window. A large sample is a single big AI call, so
# it can consume a meaningful chunk of a metered plan's token budget; the UI warns.
ANALYZE_SAMPLE_BUDGET = 128_000

LAYER_COLUMNS = {
    "core": "core_personality",
    "behavioral": "behavioral_patterns",
    "voice": "voice_fingerprint",
}

# Map the core layer (keyed by interview question ids) onto the legacy free-text
# Character columns it feeds. Deterministic string assembly — no LLM needed.
_CORE_TO_PERSONALITY = ["lie", "value_hierarchy", "self_gap", "moral_line"]
_CORE_TO_MOTIVATION = ["want", "need"]
_CORE_TO_FLAW = ["shame", "wound"]


def _join_fields(blob: dict, keys: list[str]) -> str:
    parts = []
    for k in keys:
        v = (blob or {}).get(k)
        if isinstance(v, list):
            v = ", ".join(str(x) for x in v if x)
        if v:
            parts.append(str(v).strip())
    return " ".join(parts).strip()


async def _require_character(db: AsyncSession, story_id: str, character_id: str) -> Character:
    ch = await db.get(Character, character_id)
    if ch is None or ch.story_id != story_id:
        raise NotFound("Character not found")
    return ch


async def get_identity(db: AsyncSession, story_id: str, character_id: str) -> CharacterIdentity:
    """Fetch the identity row, creating an empty one (seeded from existing
    free-text on first open) if none exists yet."""
    character = await _require_character(db, story_id, character_id)
    row = (
        await db.execute(
            select(CharacterIdentity).where(
                CharacterIdentity.story_id == story_id,
                CharacterIdentity.character_id == character_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = CharacterIdentity(story_id=story_id, character_id=character_id)
        seed_from_existing(row, character)
        db.add(row)
        await db.flush()
    return row


def seed_from_existing(identity: CharacterIdentity, character: Character) -> None:
    """Best-effort import of legacy free-text into seed layer values (no LLM).
    Only fills blanks — never clobbers structured content the author has entered."""
    if not identity.core_personality:
        core: dict = {}
        if character.personality:
            core["lie"] = character.personality
        if character.motivation:
            core["want"] = character.motivation
        if character.flaw:
            core["shame"] = character.flaw
        if core:
            identity.core_personality = core
    if not identity.short_profile and character.backstory:
        identity.short_profile = character.backstory


def compile_to_legacy(identity: CharacterIdentity, character: Character) -> None:
    """Project structured layers down into the legacy Character columns that
    context_builder + the Characters tab read. The layers are authoritative;
    these columns are a derived view kept populated for back-compat."""
    core = identity.core_personality or {}
    personality = _join_fields(core, _CORE_TO_PERSONALITY)
    if personality:
        character.personality = personality
    motivation = _join_fields(core, _CORE_TO_MOTIVATION)
    if motivation:
        character.motivation = motivation
    flaw = _join_fields(core, _CORE_TO_FLAW)
    if flaw:
        character.flaw = flaw
    if identity.short_profile:
        character.backstory = identity.short_profile


def _completeness(identity: CharacterIdentity) -> dict:
    def pct(blob: dict, fields: int) -> int:
        if not blob:
            return 0
        filled = sum(1 for v in blob.values() if v)
        return min(100, round(100 * filled / max(1, fields)))
    return {
        "core": pct(identity.core_personality, 8),
        "behavioral": pct(identity.behavioral_patterns, 7),
        "voice": pct(identity.voice_fingerprint, 7),
    }


async def _next_version_no(db: AsyncSession, story_id: str, character_id: str) -> int:
    rows = (
        await db.execute(
            select(IdentityVersion.version_no).where(
                IdentityVersion.story_id == story_id,
                IdentityVersion.character_id == character_id,
            )
        )
    ).scalars().all()
    return (max(rows) + 1) if rows else 1


async def _record_version(
    db: AsyncSession,
    story_id: str,
    character_id: str,
    kind: str,
    snapshot: dict,
    *,
    note: str = "",
    chapter_id: str | None = None,
) -> None:
    version_no = await _next_version_no(db, story_id, character_id)
    db.add(
        IdentityVersion(
            story_id=story_id,
            character_id=character_id,
            version_no=version_no,
            kind=kind,
            snapshot=snapshot or {},
            note=note[:255],
            chapter_id=chapter_id,
        )
    )
    await _prune_versions(db, story_id, character_id, kind)


async def _prune_versions(db: AsyncSession, story_id: str, character_id: str, kind: str) -> None:
    rows = (
        await db.execute(
            select(IdentityVersion)
            .where(
                IdentityVersion.story_id == story_id,
                IdentityVersion.character_id == character_id,
                IdentityVersion.kind == kind,
            )
            .order_by(IdentityVersion.version_no.desc())
        )
    ).scalars().all()
    for stale in rows[_MAX_VERSIONS_PER_KIND:]:
        await db.delete(stale)


async def patch_layer(
    db: AsyncSession,
    story_id: str,
    character_id: str,
    layer: str,
    payload: dict,
    *,
    build_method: str | None = None,
    record: bool = True,
) -> CharacterIdentity:
    """Replace one identity layer (core|behavioral|voice), refresh completeness,
    write a version snapshot, and recompile the legacy projection."""
    if layer not in LAYER_COLUMNS:
        raise NotFound(f"Unknown identity layer: {layer}")
    character = await _require_character(db, story_id, character_id)
    identity = await get_identity(db, story_id, character_id)
    setattr(identity, LAYER_COLUMNS[layer], payload or {})
    if build_method:
        identity.build_method = build_method
    identity.completeness = _completeness(identity)
    identity.updated_at = datetime.now(timezone.utc)
    compile_to_legacy(identity, character)
    if record:
        version_kind = "core" if layer == "core" else ("approved_canon" if layer == "voice" else "inferred")
        await _record_version(db, story_id, character_id, version_kind, {layer: payload})
    await db.flush()
    return identity


# ── Relationship masks (layer 4) ───────────────────────────────────────────────

async def list_masks(db: AsyncSession, story_id: str, character_id: str) -> list[RelationshipMask]:
    return list(
        (
            await db.execute(
                select(RelationshipMask).where(
                    RelationshipMask.story_id == story_id,
                    RelationshipMask.character_id == character_id,
                ).order_by(RelationshipMask.updated_at)
            )
        ).scalars().all()
    )


async def add_mask(db: AsyncSession, story_id: str, character_id: str, payload: dict) -> RelationshipMask:
    await _require_character(db, story_id, character_id)
    mask = RelationshipMask(
        story_id=story_id,
        character_id=character_id,
        audience_character_id=payload.get("audience_character_id") or None,
        audience_label=payload.get("audience_label", ""),
        speech_style=payload.get("speech_style", ""),
        tells=payload.get("tells", ""),
        notes=payload.get("notes", ""),
    )
    db.add(mask)
    await db.flush()
    return mask


async def patch_mask(db: AsyncSession, story_id: str, mask_id: str, payload: dict) -> RelationshipMask:
    mask = await db.get(RelationshipMask, mask_id)
    if mask is None or mask.story_id != story_id:
        raise NotFound("Mask not found")
    for field in ("audience_character_id", "audience_label", "speech_style", "tells", "notes"):
        if field in payload:
            setattr(mask, field, payload[field] or ("" if field != "audience_character_id" else None))
    mask.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return mask


async def delete_mask(db: AsyncSession, story_id: str, mask_id: str) -> None:
    mask = await db.get(RelationshipMask, mask_id)
    if mask is None or mask.story_id != story_id:
        raise NotFound("Mask not found")
    await db.delete(mask)


# ── Current state (layer 5) ────────────────────────────────────────────────────

async def list_states(
    db: AsyncSession, story_id: str, character_id: str, *, active_only: bool = False
) -> list[CharacterState]:
    stmt = select(CharacterState).where(
        CharacterState.story_id == story_id,
        CharacterState.character_id == character_id,
    )
    if active_only:
        stmt = stmt.where(CharacterState.active.is_(True))
    stmt = stmt.order_by(CharacterState.created_at.desc())
    return list((await db.execute(stmt)).scalars().all())


async def set_state(db: AsyncSession, story_id: str, character_id: str, payload: dict) -> CharacterState:
    await _require_character(db, story_id, character_id)
    state = CharacterState(
        story_id=story_id,
        character_id=character_id,
        chapter_id=payload.get("chapter_id") or None,
        label=payload.get("label", ""),
        detail=payload.get("detail", ""),
        kind=payload.get("kind", "temporary"),
        active=payload.get("active", True),
    )
    db.add(state)
    await _record_version(
        db, story_id, character_id, "scene_state",
        {"label": state.label, "detail": state.detail, "kind": state.kind},
        chapter_id=state.chapter_id,
    )
    await db.flush()
    return state


async def clear_state(db: AsyncSession, story_id: str, state_id: str) -> None:
    state = await db.get(CharacterState, state_id)
    if state is None or state.story_id != story_id:
        raise NotFound("State not found")
    state.active = False
    state.updated_at = datetime.now(timezone.utc)
    await db.flush()


# ── Versions / arc progression ─────────────────────────────────────────────────

async def list_versions(
    db: AsyncSession, story_id: str, character_id: str, *, kind: str | None = None
) -> list[IdentityVersion]:
    stmt = select(IdentityVersion).where(
        IdentityVersion.story_id == story_id,
        IdentityVersion.character_id == character_id,
    )
    if kind:
        stmt = stmt.where(IdentityVersion.kind == kind)
    stmt = stmt.order_by(IdentityVersion.version_no.desc())
    return list((await db.execute(stmt)).scalars().all())


async def arc_timeline(db: AsyncSession, story_id: str, character_id: str) -> list[IdentityVersion]:
    return await list_versions(db, story_id, character_id, kind="arc")


# ── Method 1: analyze existing writing ─────────────────────────────────────────

ANALYZE_SYSTEM = """You are a character voice analyst. You are given sample prose
featuring a named character AND a fixed list of QUESTIONS about that character.
Answer ONLY the questions the prose gives you real evidence for — do not invent
fields, and do not answer a question the sample doesn't support. You only PROPOSE
answers; the author approves each one. Nothing becomes canon silently.

Return ONLY a JSON object:
{
  "traits": [
    {"question_id": "<the exact id of a question you are answering>",
     "value": "<the answer, grounded in the sample, concise>",
     "confidence": 0.0-1.0,
     "excerpts": ["<short verbatim quote from the sample that supports it>"]}
  ],
  "representative_dialogue": ["<1-3 lines that best capture the voice>"],
  "uncertain_areas": ["<question topics the sample doesn't reveal>"]
}
Rules:
- "question_id" MUST be one of the provided ids. Skip questions with no evidence.
- Confidence reflects how strongly the sample supports the answer.
- Prefer fewer, well-grounded answers over many guesses.
- Base everything ONLY on the provided sample."""

INTERVIEW_SYNTH_SYSTEM = """You are a character designer. The author answered a
layered interview about their character (each answer is tagged with its layer:
core / behavioral / voice / relationship / current). Turn the answers into a
coherent five-layer identity.

Return ONLY a JSON object. Use these EXACT layer keys (they match the interview
question ids, so the editor and the AI context can read them):
{
  "short_profile": "<2-4 sentence readable summary of who this character is>",
  "core_personality": {"want": "", "need": "", "lie": "", "wound": "", "shame": "",
     "value_hierarchy": "", "moral_line": "", "self_gap": ""},
  "behavioral_patterns": {"stress_response": "", "vulnerability": "", "criticism": "",
     "deception": "", "decision_tempo": "", "anger_tell": "", "recovery": ""},
  "voice_fingerprint": {"cadence": "", "directness": "", "lexicon": "", "emotion_shift": "",
     "register": "", "silence": "", "humor": "",
     "shifts": {"angry": "", "frightened": "", "relaxed": "", "with_authority": ""}},
  "relationship_masks": [
     {"audience_label": "<who, e.g. 'an authority they need', 'their safe person'>",
      "speech_style": "<how their voice changes for this audience>",
      "tells": "<what leaks through, if any>"}
  ],
  "current_state": [
     {"label": "<short state, e.g. 'grieving', 'on a deadline'>",
      "detail": "<how it colors the scene>",
      "kind": "temporary|recurring|arc"}
  ]
}
Rules:
- Only fill fields the answers support; leave the rest empty / arrays empty.
- relationship_masks: derive ONE entry per relationship answer that describes an
  audience-specific voice. Keep speech_style as how they SOUND to that audience.
- current_state: derive from the 'current' answers ONLY. Default kind to
  "temporary" unless the author marked a chapter/arc duration.
- Keep values concise and specific. Do not invent facts the author didn't imply."""


async def _assemble_sample(
    db: AsyncSession, story_id: str, chapter_ids: list[str], text: str
) -> tuple[str, list[dict], bool]:
    """Build the analysis sample from selected chapters (in chapter-number order)
    plus any pasted text, packed under ANALYZE_SAMPLE_BUDGET. Returns
    (sample, used_chapters, truncated). Whole chapters are kept until the budget is
    hit; the chapter that overflows is partially included with a marker."""
    parts: list[str] = []
    used: list[dict] = []
    budget = ANALYZE_SAMPLE_BUDGET
    truncated = False

    if chapter_ids:
        rows = (
            await db.execute(
                select(Chapter).where(
                    Chapter.story_id == story_id, Chapter.id.in_(chapter_ids)
                ).order_by(Chapter.number)
            )
        ).scalars().all()
        for ch in rows:
            if budget <= 0:
                truncated = True
                break
            header = f"## Chapter {ch.number}: {ch.title or '(untitled)'}\n"
            body = ch.content or ""
            avail = budget - len(header)
            if avail <= 0:
                truncated = True
                break
            if len(body) > avail:
                body = body[:avail].rstrip() + "\n…[truncated]"
                truncated = True
            chunk = header + body
            parts.append(chunk)
            budget -= len(chunk)
            used.append({"id": ch.id, "number": ch.number, "title": ch.title or ""})

    pasted = (text or "").strip()
    if pasted and budget > 0:
        if len(pasted) > budget:
            pasted = pasted[:budget].rstrip() + "\n…[truncated]"
            truncated = True
        parts.append(pasted if not parts else "## Pasted text\n" + pasted)
    elif pasted and budget <= 0:
        truncated = True

    return "\n\n".join(parts).strip(), used, truncated


async def analyze_writing(
    db: AsyncSession, user: User, story_id: str, character_id: str,
    text: str = "", chapter_ids: list[str] | None = None,
) -> dict:
    """Method 1 — propose identity traits from a prose sample (selected chapters
    and/or pasted text), packed under ANALYZE_SAMPLE_BUDGET. Commits nothing."""
    character = await _require_character(db, story_id, character_id)
    sample, used_chapters, truncated = await _assemble_sample(
        db, story_id, chapter_ids or [], text
    )
    if not sample:
        return {"traits": [], "representative_dialogue": [], "uncertain_areas": [],
                "used_chapters": [], "truncated": False, "fallback": False}

    ctx = await build_story_context(db, story_id)
    user_msg = (
        "STORY CONTEXT (reference only):\n"
        f"{fence('story_context', ctx)}\n\n"
        f"CHARACTER TO ANALYZE: {character.name}\n\n"
        "WRITING SAMPLE:\n"
        f"{fence('author_text', sample)}"
    )
    from app.services.identity_questions import QUESTIONS_BY_ID, extractable_questions

    questions = extractable_questions()
    q_block = "\n".join(f'- {q["id"]} [{q["layer"]}]: {q["text"]}' for q in questions)
    user_msg += "\n\nQUESTIONS TO ANSWER (use the exact question_id; skip any with no evidence):\n" + q_block

    resp, fb = await llm_service.run(
        db, user, page="voice.analyze", system=ANALYZE_SYSTEM + "\n\n" + SECURITY_CLAUSE,
        user_msg=user_msg, json_mode=True, temperature=0.2, max_tokens=6000, story_id=story_id,
    )
    parsed = llm_service.parse_json(resp.text) or {}
    if not isinstance(parsed, dict):
        parsed = {}
    traits = []
    for t in (parsed.get("traits") or []):
        if not isinstance(t, dict):
            continue
        # Normalize: models sometimes echo the id as "lie [core]" or "lie (core)"
        # or with stray whitespace. Strip any trailing "[...]"/"(...)" tag.
        qid = re.sub(r"\s*[\[(].*$", "", str(t.get("question_id", ""))).strip()
        q = QUESTIONS_BY_ID.get(qid)
        # Only accept answers to real, extractable questions — the field key IS the
        # question id, so analyze / interview / editor / context share one vocabulary.
        if q is None or q["layer"] not in LAYER_COLUMNS:
            continue
        try:
            conf = float(t.get("confidence", 0.0))
        except (TypeError, ValueError):
            conf = 0.0
        excerpts = [str(x) for x in (t.get("excerpts") or []) if x][:3]
        traits.append({
            "layer": q["layer"],
            "field": qid,
            "question": q["text"],
            "value": t.get("value", ""),
            "confidence": max(0.0, min(1.0, conf)),
            "excerpts": excerpts,
            "status": "proposed",
        })
    return {
        "traits": traits,
        "representative_dialogue": [str(x) for x in (parsed.get("representative_dialogue") or []) if x][:5],
        "uncertain_areas": [str(x) for x in (parsed.get("uncertain_areas") or []) if x][:8],
        "used_chapters": used_chapters,
        "truncated": truncated,
        "fallback": fb,
    }


async def approve_traits(db: AsyncSession, story_id: str, character_id: str, decisions: list[dict]) -> CharacterIdentity:
    """Commit author-approved traits into the right layers. Reject/edit handled by
    the caller (only approved decisions reach here). Merges into existing layers."""
    character = await _require_character(db, story_id, character_id)
    identity = await get_identity(db, story_id, character_id)
    touched: set[str] = set()
    for d in decisions:
        if d.get("decision") != "approve":
            continue
        layer = d.get("layer")
        field = d.get("field")
        if layer not in LAYER_COLUMNS or not field:
            continue
        col = LAYER_COLUMNS[layer]
        blob = dict(getattr(identity, col) or {})
        blob[field] = d.get("value", "")
        setattr(identity, col, blob)
        touched.add(layer)
    if touched:
        identity.build_method = "analyze"
        identity.completeness = _completeness(identity)
        identity.updated_at = datetime.now(timezone.utc)
        compile_to_legacy(identity, character)
        await _record_version(db, story_id, character_id, "approved_canon",
                              {"layers": sorted(touched)}, note="from analyze")
        await db.flush()
    return identity


# ── Method 2: guided interview ─────────────────────────────────────────────────

async def synthesize_from_interview(
    db: AsyncSession, user: User, story_id: str, character_id: str, answers: dict, tier: str
) -> CharacterIdentity:
    """Method 2 — turn layered interview answers into all five identity layers and a
    readable short profile, then persist: core/behavioral/voice into CharacterIdentity
    JSON, relationship answers into RelationshipMask rows, current answers into
    CharacterState rows. A one-off scene state never becomes core canon."""
    from app.services.identity_questions import QUESTIONS_BY_ID

    character = await _require_character(db, story_id, character_id)
    # Tag each answer with its layer so the model routes it correctly.
    lines = []
    for qid, val in (answers or {}).items():
        if not val:
            continue
        layer = (QUESTIONS_BY_ID.get(qid) or {}).get("layer", "core")
        lines.append(f"- [{layer}] {qid}: {val}")
    answer_lines = "\n".join(lines)
    user_msg = (
        f"CHARACTER: {character.name}\n\n"
        "INTERVIEW ANSWERS (tagged by layer):\n"
        f"{fence('author_text', answer_lines)}"
    )
    resp, fb = await llm_service.run(
        db, user, page="voice.interview", system=INTERVIEW_SYNTH_SYSTEM + "\n\n" + SECURITY_CLAUSE,
        user_msg=user_msg, json_mode=True, temperature=0.4, max_tokens=4000, story_id=story_id,
    )
    parsed = llm_service.parse_json(resp.text) or {}
    if not isinstance(parsed, dict):
        parsed = {}

    identity = await get_identity(db, story_id, character_id)
    if isinstance(parsed.get("core_personality"), dict):
        identity.core_personality = {**(identity.core_personality or {}), **parsed["core_personality"]}
    if isinstance(parsed.get("behavioral_patterns"), dict):
        identity.behavioral_patterns = {**(identity.behavioral_patterns or {}), **parsed["behavioral_patterns"]}
    if isinstance(parsed.get("voice_fingerprint"), dict):
        identity.voice_fingerprint = {**(identity.voice_fingerprint or {}), **parsed["voice_fingerprint"]}
    if parsed.get("short_profile"):
        identity.short_profile = str(parsed["short_profile"])

    # Relationship masks → their own table (layer 4 has natural multiplicity).
    for m in (parsed.get("relationship_masks") or []):
        if not isinstance(m, dict):
            continue
        style = str(m.get("speech_style", "")).strip()
        label = str(m.get("audience_label", "")).strip()
        if not style or not label:
            continue
        db.add(RelationshipMask(
            story_id=story_id, character_id=character_id,
            audience_label=label[:120], speech_style=style, tells=str(m.get("tells", "")),
        ))

    # Current state → scene-scoped rows (layer 5 must not pollute core canon).
    for s in (parsed.get("current_state") or []):
        if not isinstance(s, dict):
            continue
        label = str(s.get("label", "")).strip()
        if not label:
            continue
        kind = s.get("kind") if s.get("kind") in ("temporary", "recurring", "arc") else "temporary"
        db.add(CharacterState(
            story_id=story_id, character_id=character_id,
            label=label[:120], detail=str(s.get("detail", "")), kind=kind, active=True,
        ))

    # Fallback path (model returned nothing): preserve the author's raw answers so
    # their work isn't lost, split by layer where possible.
    if not parsed and answer_lines:
        identity.core_personality = {**(identity.core_personality or {}), "interview_notes": answer_lines}

    identity.build_method = "interview"
    identity.completeness = _completeness(identity)
    identity.updated_at = datetime.now(timezone.utc)
    compile_to_legacy(identity, character)
    await _record_version(db, story_id, character_id, "core", {"interview": True}, note=f"interview/{tier}")
    await db.flush()
    return identity
