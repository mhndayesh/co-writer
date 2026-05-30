from fastapi import APIRouter
from sqlalchemy import desc, select

from app.core.deps import CurrentUser, DB, get_user_story
from app.core.errors import envelope_ok
from app.db.models import Chapter, FlowDraft
from app.db.schemas import (
    ChapterOut,
    CompanionRequest,
    CompanionResponse,
    FlowApproveRequest,
    FlowApproveResponse,
    FlowExtractRequest,
    FlowExtractResponse,
    FlowPolishRequest,
    FlowPolishResponse,
)
from app.services import flow_service, llm_service
from app.services.context_builder import build_story_context

router = APIRouter()


@router.post("/{story_id}/flow/polish")
async def flow_polish(story_id: str, payload: FlowPolishRequest, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    resp = await flow_service.polish(db, user, story_id, payload.raw, payload.notes)
    await db.commit()
    return envelope_ok(resp.model_dump())


@router.post("/{story_id}/flow/extract")
async def flow_extract(story_id: str, payload: FlowExtractRequest, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    resp = await flow_service.extract(db, user, story_id, payload.polished)
    await db.commit()
    return envelope_ok(resp.model_dump())


@router.post("/{story_id}/flow/approve")
async def flow_approve(story_id: str, payload: FlowApproveRequest, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    chapter, new_ids, themes, version_no = await flow_service.approve(db, user, story_id, payload)
    return envelope_ok(FlowApproveResponse(
        chapter_id=chapter.id,
        new_character_ids=new_ids,
        added_themes=themes,
        version_no=version_no,
    ).model_dump())


@router.post("/{story_id}/flow/draft")
async def flow_save_draft(story_id: str, payload: dict, user: CurrentUser, db: DB):
    """Autosave the in-progress raw draft so the user never loses work."""
    await get_user_story(story_id, user, db)
    draft = (await db.execute(
        select(FlowDraft).where(FlowDraft.story_id == story_id, FlowDraft.approved_at.is_(None)).order_by(desc(FlowDraft.updated_at))
    )).scalar_one_or_none()
    if draft is None:
        draft = FlowDraft(story_id=story_id)
        db.add(draft)
    draft.raw = payload.get("raw", "") or ""
    draft.polished = payload.get("polished", "") or ""
    draft.notes = payload.get("notes", "") or ""
    if isinstance(payload.get("extracted"), dict):
        draft.extracted = payload["extracted"]
    await db.commit()
    await db.refresh(draft)
    return envelope_ok({"draft_id": draft.id})


@router.get("/{story_id}/flow/draft")
async def flow_get_draft(story_id: str, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    draft = (await db.execute(
        select(FlowDraft).where(FlowDraft.story_id == story_id, FlowDraft.approved_at.is_(None)).order_by(desc(FlowDraft.updated_at))
    )).scalar_one_or_none()
    if draft is None:
        return envelope_ok({"draft": None})
    return envelope_ok({
        "draft": {
            "id": draft.id,
            "raw": draft.raw,
            "polished": draft.polished,
            "notes": draft.notes,
            "extracted": draft.extracted,
        }
    })


@router.delete("/{story_id}/flow/draft")
async def flow_clear_draft(story_id: str, user: CurrentUser, db: DB):
    """Discard the in-progress draft. Marks all unfinished drafts for this
    story as approved so the next Flow Writing session starts blank.
    Idempotent — safe to call when there's nothing to clear."""
    from datetime import datetime, timezone

    await get_user_story(story_id, user, db)
    drafts = (await db.execute(
        select(FlowDraft).where(FlowDraft.story_id == story_id, FlowDraft.approved_at.is_(None))
    )).scalars().all()
    now = datetime.now(timezone.utc)
    for d in drafts:
        d.approved_at = now
    await db.commit()
    return envelope_ok({"cleared": len(drafts)})


COMPANION_SYSTEM = """You are a Writing Companion. The author gives an instruction (e.g.
"draft a scene where Aiden confronts Mira about the broken pact"). Use the STORY CONTEXT
and any GRAPH CONTEXT to produce a polished scene that respects the world rules, character
voices, and prior events.

Return polished prose only. No headers, no analysis, no commentary."""


@router.post("/{story_id}/flow/companion")
async def writing_companion(story_id: str, payload: CompanionRequest, user: CurrentUser, db: DB):
    """Graph-RAG-powered Writing Companion (Chapters tab)."""
    await get_user_story(story_id, user, db)

    # Optional graph slice via RAG
    graph_block = ""
    try:
        from app.services import rag_service

        graph_block = await rag_service.retrieve_context_block(db, user, story_id, payload.instruction)
    except Exception:
        graph_block = ""

    ctx = await build_story_context(db, story_id, extra_graph_block=graph_block)
    user_msg = f"STORY CONTEXT:\n{ctx}\n\nAUTHOR INSTRUCTION:\n{payload.instruction}"
    resp, fb = await llm_service.run(
        db, user, page="flow.companion", system=COMPANION_SYSTEM, user_msg=user_msg,
        temperature=0.8, max_tokens=None, story_id=story_id,
    )
    await db.commit()
    return envelope_ok(CompanionResponse(draft=resp.text.strip(), fallback=fb).model_dump())
