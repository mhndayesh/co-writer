"""Graph-RAG: combine Qdrant vector hits with Neo4j 1-hop subgraphs.

Returns a Markdown context block to splice into LLM prompts via
context_builder.build_story_context(extra_graph_block=...).

Falls back gracefully:
  • If embedding fails → returns ""
  • If Qdrant down    → returns Neo4j subgraph only
  • If Neo4j down     → returns vector hits only
  • If both down      → returns ""
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Character, User
from app.services import embedding_service, graph_service

log = logging.getLogger("gink.rag")


async def retrieve_context_block(
    db: AsyncSession,
    user: User,
    story_id: str,
    query: str,
    *,
    top_k_chunks: int = 6,
    hops: int = 1,
) -> str:
    """Build a structured context block from vector hits + graph subgraphs."""
    from app.services import llm_service

    # 1) Embed query (metered when house-paid; BYOK uses the user's own embedder)
    chunks: list[dict] = []
    try:
        qvec = (await llm_service.embed(db, user, [query], story_id=story_id))[0]
        chunks = await embedding_service.search(story_id, qvec, top_k=top_k_chunks)
    except Exception as e:
        log.debug("rag embed/search failed: %s", e)

    # 2) Find character mentions to seed subgraph queries
    chars = (await db.execute(select(Character).where(Character.story_id == story_id))).scalars().all()
    by_lower_name = {c.name.lower(): c for c in chars}
    mentioned_ids: set[str] = set()
    q_lower = query.lower()
    for name, c in by_lower_name.items():
        if name and name in q_lower:
            mentioned_ids.add(c.id)
    # Also use top-scoring char chunks
    for ch in chunks:
        if ch.get("kind") == "character" and ch.get("character_id"):
            mentioned_ids.add(ch["character_id"])
    mentioned_ids = set(list(mentioned_ids)[:4])  # cap

    # 3) Subgraph slices
    subgraph_lines: list[str] = []
    for cid in mentioned_ids:
        lines = await graph_service.subgraph_for_character(story_id, cid, hops=hops)
        subgraph_lines.extend(lines)

    if not chunks and not subgraph_lines:
        return ""

    parts: list[str] = []
    if chunks:
        parts.append("## Semantic matches")
        for c in chunks:
            kind = c.get("kind", "?")
            label = ""
            if kind == "chapter":
                label = f"Ch{c.get('number','?')}. {c.get('title','')}"
            elif kind == "character":
                label = f"Character: {c.get('name','')}"
            elif kind == "scene":
                label = "Scene: " + (c.get("title") or f"#{c.get('ordinal', '')}")
            txt = (c.get("text", "") or "")[:500]
            parts.append(f"- ({kind}) {label} — {txt}")

    if subgraph_lines:
        parts.append("")
        parts.append("## Graph neighborhood")
        for line in subgraph_lines[:30]:
            parts.append(f"- {line}")

    return "\n".join(parts).strip()
