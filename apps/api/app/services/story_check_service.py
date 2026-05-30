"""Continuity validator — reads a chapter against the full world + cast + history.

Uses Graph-RAG to pull in semantically-related chunks and 1-hop neighborhoods
of the characters that appear in the chapter, so subtle inconsistencies
("Mira was killed in Ch3 but is alive again in Ch7") surface.
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chapter, ContinuityReport, User
from app.db.schemas import CheckFinding, RevisionPass, StoryCheckResponse
from app.services import llm_service, rag_service
from app.services.context_builder import build_story_context

log = logging.getLogger("gink.check")

PASS_GUIDANCE: dict[str, str] = {
    "structure": "Focus on scene purpose, setup/payoff, pacing, escalation, dormant subplots, and whether each scene changes the story state.",
    "character": "Focus on motivation, agency, arc movement, relationship shifts, impossible knowledge, and whether choices match established character state.",
    "logic": "Focus on continuity, timeline order, world rules, causal logic, spatial logic, information flow, and contradictions.",
    "dialogue": "Focus on character voice fingerprints, dialogue attribution, voice drift, characters sounding too similar, and subtext.",
    "tightening": "Focus on repetition, unclear beats, overwritten passages, missing sensory contrast, and opportunities to sharpen without changing plot facts.",
}

SYSTEM = """You are a story check editor. You will be given a STORY CONTEXT (world bible,
cast, chapters, scene cards, revelations, voice fingerprints, graph slice), then a target
chapter or manuscript-wide target to review.

Run the requested revision pass only. Ground findings in stored story facts and cite
chapter/scene IDs when the data gives you enough confidence. Also call out what's working well.

Return ONLY a JSON object:
{
  "findings": [
    {"severity": "high"|"medium"|"low", "title": "...", "detail": "...", "suggestion": "...", "chapter_id": null, "scene_id": null}
  ],
  "strengths": ["..."],
  "severity_buckets": {"high": N, "medium": N, "low": N}
}

Severity guide:
  high   = contradicts established facts (character death, world rule violation, timeline impossibility)
  medium = unexplained shift, missing setup/payoff, voice or POV inconsistency
  low    = stylistic note, minor opportunity to deepen tie-ins
"""


async def check(
    db: AsyncSession,
    user: User,
    story_id: str,
    chapter_id: str | None,
    pass_type: RevisionPass = "logic",
) -> StoryCheckResponse:
    chapter: Chapter | None = None
    if chapter_id:
        chapter = await db.get(Chapter, chapter_id)
    if chapter_id and (chapter is None or chapter.story_id != story_id):
        raise ValueError("chapter not found")

    # Pull a graph slice keyed on the chapter content (uses character mentions to find subgraphs)
    query = (
        f"{chapter.title}\n{chapter.summary}\n{chapter.content[:2000]}"
        if chapter is not None
        else f"Story Check {pass_type} pass"
    )
    graph_block = ""
    try:
        graph_block = await rag_service.retrieve_context_block(db, user, story_id, query)
    except Exception as e:
        log.debug("rag block failed: %s", e)

    ctx = await build_story_context(db, story_id, include_chapter_bodies=False, extra_graph_block=graph_block)

    target = (
        f"TARGET CHAPTER (id={chapter.id}, Ch{chapter.number}: {chapter.title}):\n{chapter.content}"
        if chapter is not None
        else "TARGET: Manuscript-wide pass. Use the full STORY CONTEXT and stored scene/revelation data."
    )
    user_msg = (
        f"REVISION PASS: {pass_type}\n"
        f"PASS FOCUS: {PASS_GUIDANCE[pass_type]}\n\n"
        f"STORY CONTEXT:\n{ctx}\n\n{target}"
    )
    resp, fb = await llm_service.run(
        db, user, page=f"story_check.{pass_type}", system=SYSTEM, user_msg=user_msg,
        json_mode=True, temperature=0.3, max_tokens=None, story_id=story_id,
    )
    parsed = llm_service.parse_json(resp.text) or {}
    if not isinstance(parsed, dict):
        parsed = {}

    findings_raw = parsed.get("findings") or []
    findings: list[CheckFinding] = []
    for f in findings_raw:
        if not isinstance(f, dict):
            continue
        sev = f.get("severity", "low")
        if sev not in ("high", "medium", "low"):
            sev = "low"
        findings.append(CheckFinding(
            severity=sev,
            title=f.get("title", "")[:200],
            detail=f.get("detail", ""),
            suggestion=f.get("suggestion", "") or "",
            chapter_id=f.get("chapter_id") if isinstance(f.get("chapter_id"), str) else chapter_id,
            scene_id=f.get("scene_id") if isinstance(f.get("scene_id"), str) else None,
        ))

    strengths = [s for s in (parsed.get("strengths") or []) if isinstance(s, str)]
    buckets = parsed.get("severity_buckets") or {}
    if not buckets:
        buckets = {
            "high": sum(1 for x in findings if x.severity == "high"),
            "medium": sum(1 for x in findings if x.severity == "medium"),
            "low": sum(1 for x in findings if x.severity == "low"),
        }

    # Persist
    report = ContinuityReport(
        story_id=story_id,
        chapter_id=chapter_id,
        severity_buckets=buckets,
        findings=[f.model_dump() for f in findings],
        strengths=strengths,
    )
    db.add(report)

    return StoryCheckResponse(
        chapter_id=chapter_id,
        pass_type=pass_type,
        findings=findings,
        strengths=strengths,
        severity_buckets=buckets,
        fallback=fb,
    )
