from fastapi import APIRouter

from app.core.deps import CurrentUser, DB, get_user_story
from app.core.errors import envelope_ok
from app.services import embedding_service, rag_service
from app.services.llm.factory import get_embedding_provider

router = APIRouter()


@router.get("/{story_id}/rag/preview")
async def preview(story_id: str, q: str, user: CurrentUser, db: DB):
    """Debug: see exactly what Graph-RAG would feed the LLM for query `q`."""
    await get_user_story(story_id, user, db)
    block = await rag_service.retrieve_context_block(db, user, story_id, q)
    return envelope_ok({"query": q, "block": block})


@router.post("/{story_id}/rag/reindex")
async def reindex(story_id: str, user: CurrentUser, db: DB):
    """(Re-)embed all chapters + character profiles into Qdrant for this story."""
    await get_user_story(story_id, user, db)
    provider = await get_embedding_provider(db, user)
    res = await embedding_service.index_story(db, user, story_id, provider)
    return envelope_ok(res)
