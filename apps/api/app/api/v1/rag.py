from fastapi import APIRouter

from app.core.deps import CurrentUser, DB, get_user_story
from app.core.errors import envelope_ok, QuotaExceeded, PaymentRequired
from app.services import embedding_service, rag_service, entitlement_service

router = APIRouter()


async def _check_embed_entitlement(db, user) -> None:
    """Gate embedding calls against the user's AI entitlement.

    Embeddings use the house key for free/dev_ai users — without this check a
    quota-exhausted user can hammer /rag/reindex and burn your embedding budget
    indefinitely with no metering or cost attribution.
    """
    auth = await entitlement_service.authorize_ai(db, user, "rag.embed", meter=False)
    if not auth.allowed:
        if auth.reason == "trial_exhausted":
            raise PaymentRequired(auth.message, details={"reason": auth.reason})
        raise QuotaExceeded(auth.message, details={"reason": auth.reason})


@router.get("/{story_id}/rag/preview")
async def preview(story_id: str, q: str, user: CurrentUser, db: DB):
    """Debug: see exactly what Graph-RAG would feed the LLM for query `q`."""
    await get_user_story(story_id, user, db)
    await _check_embed_entitlement(db, user)
    block = await rag_service.retrieve_context_block(db, user, story_id, q)
    return envelope_ok({"query": q, "block": block})


@router.post("/{story_id}/rag/reindex")
async def reindex(story_id: str, user: CurrentUser, db: DB):
    """(Re-)embed all chapters + character profiles into Qdrant for this story."""
    await get_user_story(story_id, user, db)
    await _check_embed_entitlement(db, user)
    res = await embedding_service.index_story(db, user, story_id)
    return envelope_ok(res)
