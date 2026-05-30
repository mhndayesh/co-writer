"""Chunk + embed story content into Qdrant. Used by RAG retrieval.

No-op if Qdrant is unreachable — RAG falls back to plain context.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import Chapter, Character, User
from app.services.llm.base import LLMProvider

log = logging.getLogger("gink.embed")

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    s = get_settings()
    if not s.qdrant_url:
        return None
    try:
        from qdrant_client import AsyncQdrantClient

        _client = AsyncQdrantClient(url=s.qdrant_url)
        return _client
    except Exception as e:
        log.warning("qdrant init failed: %s", e)
        return None


def _collection(story_id: str) -> str:
    return f"story_{story_id}_chunks"


def _chunk_text(text: str, *, target: int = 1200, overlap: int = 120) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= target:
        return [text]
    chunks: list[str] = []
    i = 0
    while i < len(text):
        chunks.append(text[i : i + target])
        i += target - overlap
    return chunks


async def ensure_collection(client, name: str, dim: int) -> None:
    from qdrant_client.http.models import Distance, VectorParams

    existing = {c.name for c in (await client.get_collections()).collections}
    if name not in existing:
        await client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )


async def index_story(db: AsyncSession, user: User, story_id: str, provider: LLMProvider) -> dict:
    """(Re-)embed all chapters + character profiles for a story."""
    client = _get_client()
    if client is None:
        return {"indexed": 0, "reason": "qdrant_unavailable"}

    chapters = (await db.execute(select(Chapter).where(Chapter.story_id == story_id))).scalars().all()
    characters = (await db.execute(select(Character).where(Character.story_id == story_id))).scalars().all()

    texts: list[str] = []
    payloads: list[dict] = []
    for ch in chapters:
        for idx, chunk in enumerate(_chunk_text(ch.content)):
            texts.append(chunk)
            payloads.append({"kind": "chapter", "chapter_id": ch.id, "chunk_idx": idx, "title": ch.title, "number": ch.number})
    for c in characters:
        profile = "\n".join(filter(None, [
            f"Name: {c.name}",
            f"Role: {c.role}",
            f"Personality: {c.personality}",
            f"Backstory: {c.backstory}",
            f"Motivation: {c.motivation}",
            f"Arc: {c.arc}",
        ]))
        if profile.strip():
            texts.append(profile)
            payloads.append({"kind": "character", "character_id": c.id, "name": c.name})

    if not texts:
        return {"indexed": 0, "reason": "empty"}

    try:
        vectors = await provider.embed(texts)
    except Exception as e:
        log.warning("embed failed: %s", e)
        return {"indexed": 0, "reason": f"embed_failed:{e}"}
    if not vectors:
        return {"indexed": 0, "reason": "no_vectors"}

    dim = len(vectors[0])
    name = _collection(story_id)
    try:
        # Wipe and recreate to avoid stale chunks; cheap because story is small
        try:
            await client.delete_collection(collection_name=name)
        except Exception:
            pass
        await ensure_collection(client, name, dim)
        from qdrant_client.http.models import PointStruct

        points = [
            PointStruct(id=i, vector=vec, payload={"text": texts[i], **payloads[i]})
            for i, vec in enumerate(vectors)
        ]
        await client.upsert(collection_name=name, points=points)
        return {"indexed": len(points)}
    except Exception as e:
        log.warning("qdrant upsert failed: %s", e)
        return {"indexed": 0, "reason": str(e)}


async def search(story_id: str, query_vector: list[float], *, top_k: int = 8) -> list[dict]:
    client = _get_client()
    if client is None:
        return []
    try:
        res = await client.search(
            collection_name=_collection(story_id),
            query_vector=query_vector,
            limit=top_k,
        )
        return [{"score": p.score, **(p.payload or {})} for p in res]
    except Exception as e:
        log.debug("qdrant search failed: %s", e)
        return []
