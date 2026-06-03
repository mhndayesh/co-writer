"""Chunk + embed story content into Qdrant. Used by RAG retrieval.

All stories share ONE collection (`gink_chunks`), partitioned by a `story_id`
payload field with a keyword index — the standard multi-tenant vector pattern.
The old design used a collection per story, which meant a separate HNSW graph and
a `create_collection` round-trip for every story, and made cross-story retrieval
impossible. A single filtered collection scales far better; a story is re-indexed
by deleting just its points (never the whole collection).

Content is chunked on natural boundaries (paragraph → sentence) so a retrieved
chunk never cuts mid-sentence, and each scene card is embedded as ONE point so a
scene is always retrieved whole rather than sliced across arbitrary windows.

No-op if Qdrant is unreachable — RAG falls back to plain context.
"""
from __future__ import annotations

import logging
import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import Chapter, Character, SceneCard, User

log = logging.getLogger("gink.embed")

# One shared collection for every story; rows are partitioned by `story_id`.
COLLECTION = "gink_chunks"
# Fixed namespace so a point's id is a deterministic function of what it embeds —
# re-indexing overwrites the same id instead of duplicating. (Integer ids, the old
# scheme, would collide across stories in a shared collection.)
_ID_NS = uuid.UUID("6f3c1e2a-9b7d-4f0a-bc11-3e6a9c2d5f80")

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


def _point_id(story_id: str, kind: str, ref: str, idx: int) -> str:
    """Deterministic UUID point id, unique per (story, kind, ref, chunk)."""
    return str(uuid.uuid5(_ID_NS, f"{story_id}|{kind}|{ref}|{idx}"))


# Sentence boundaries across scripts: ASCII .!? need trailing whitespace, but CJK
# 。！？ and Arabic ؟ often have none — allow a zero-width split right after them so
# non-Latin prose isn't treated as one boundary-less blob (which forces mid-word
# hard-splits). The two terminator sets are disjoint, so they never double-split.
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|(?<=[。！？؟])\s*")
# Split on any run of newlines, so single-newline-separated paragraphs each become
# their own unit instead of one giant block.
_PARA_SPLIT = re.compile(r"\n+")


def _chunk_text(text: str, *, target: int = 1200, overlap_sentences: int = 1) -> list[str]:
    """Split `text` into chunks of ~`target` chars on natural boundaries.

    Packs whole paragraphs; when a paragraph alone exceeds `target` it falls back
    to packing whole sentences; only a single sentence longer than `target` is
    hard-split as a last resort. So a chunk never cuts mid-sentence in the common
    case (the old fixed-window slicer cut mid-word). A small trailing unit is
    carried into the next chunk for retrieval continuity.
    """
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= target:
        return [text]

    # 1) Break into ordered units no larger than `target`.
    units: list[str] = []
    for para in _PARA_SPLIT.split(text):
        para = para.strip()
        if not para:
            continue
        if len(para) <= target:
            units.append(para)
            continue
        # Paragraph too big — pack its sentences.
        sent = ""
        for s in _SENT_SPLIT.split(para):
            s = s.strip()
            if not s:
                continue
            if len(s) > target:
                if sent:
                    units.append(sent)
                    sent = ""
                for i in range(0, len(s), target):
                    units.append(s[i : i + target])
            elif not sent:
                sent = s
            elif len(sent) + 1 + len(s) <= target:
                sent = sent + " " + s
            else:
                units.append(sent)
                sent = s
        if sent:
            units.append(sent)

    # 2) Greedily pack units into chunks, carrying a small trailing unit forward.
    chunks: list[str] = []
    cur: list[str] = []
    for u in units:
        # Approx length of cur joined by "\n\n" (2 chars between units) plus u.
        if cur and sum(len(x) for x in cur) + 2 * len(cur) + len(u) > target:
            chunks.append("\n\n".join(cur))
            # Only carry small units forward (avoid duplicating a near-target unit).
            cur = [x for x in cur[-overlap_sentences:] if len(x) < target // 2] if overlap_sentences else []
        cur.append(u)
    if cur:
        chunks.append("\n\n".join(cur))
    return chunks


def _scene_text(sc: SceneCard) -> str:
    """A self-contained embedding text for one scene card (never split).

    Returns "" for a scene with no substantive content so we don't index a bare
    "Scene:" header as noise.
    """
    # Strip every field first so a whitespace-only scene yields "" (no bare "Scene:").
    summary = (sc.summary or "").strip()
    goal = (sc.goal or "").strip()
    conflict = (sc.conflict or "").strip()
    outcome = (sc.outcome or "").strip()
    content = (sc.content or "").strip()
    excerpt = (sc.source_excerpt or "").strip()
    title = (sc.title or "").strip()
    beat = (sc.beat or "").strip()

    body: list[str] = []
    if summary:
        body.append(summary)
    detail = " / ".join(
        x for x in [
            f"Goal: {goal}" if goal else "",
            f"Conflict: {conflict}" if conflict else "",
            f"Outcome: {outcome}" if outcome else "",
        ] if x
    )
    if detail:
        body.append(detail)
    if content:
        body.append(content)
    if excerpt:
        body.append(excerpt)

    head = title or beat
    if not head and not body:
        return ""
    lines = [f"Scene: {head or 'Scene'}"]
    if beat and beat != head:
        lines.append(f"Beat: {beat}")
    lines.extend(body)
    return "\n".join(lines).strip()


async def ensure_collection(client, name: str, dim: int) -> bool:
    """Create the shared collection + story_id payload index if missing.

    Returns False if an existing collection's vector size doesn't match `dim`
    (you can't mix embedding dimensions in one collection) so the caller skips
    indexing rather than throwing on every upsert.
    """
    from qdrant_client.http.models import Distance, PayloadSchemaType, VectorParams

    existing = {c.name for c in (await client.get_collections()).collections}
    if name not in existing:
        await client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
    else:
        # Existing collection — refuse to mix vector dimensions.
        try:
            info = await client.get_collection(name)
            # `.vectors` is a VectorParams (single unnamed vector, our case) with a
            # `.size`, OR a dict for named vectors — getattr handles both without
            # raising (None → skip the check rather than swallow an AttributeError).
            size = getattr(info.config.params.vectors, "size", None)
            if size and dim and size != dim:
                log.warning("qdrant collection %s dim %s != provider dim %s; skipping index", name, size, dim)
                return False
        except Exception as e:
            log.debug("get_collection inspect failed: %s", e)

    # Always (re)ensure the story_id payload index — idempotent, and covers a
    # collection created before this index existed (the perf path for the filter).
    try:
        await client.create_payload_index(
            collection_name=name, field_name="story_id", field_schema=PayloadSchemaType.KEYWORD
        )
    except Exception as e:  # index is an optimization; upserts/filters still work without it
        log.debug("payload index ensure failed: %s", e)
    return True


async def _delete_story_points(client, story_id: str) -> None:
    """Remove just this story's points from the shared collection."""
    from qdrant_client.http.models import FieldCondition, Filter, FilterSelector, MatchValue

    try:
        await client.delete(
            collection_name=COLLECTION,
            points_selector=FilterSelector(
                filter=Filter(must=[FieldCondition(key="story_id", match=MatchValue(value=story_id))])
            ),
        )
    except Exception as e:
        log.debug("delete story points failed: %s", e)


async def _drop_legacy_collection(client, story_id: str) -> None:
    """Best-effort cleanup of the old per-story collection after migrating."""
    legacy = f"story_{story_id}_chunks"
    try:
        existing = {c.name for c in (await client.get_collections()).collections}
        if legacy in existing:
            await client.delete_collection(collection_name=legacy)
    except Exception as e:
        log.debug("legacy collection cleanup failed: %s", e)


async def index_story(db: AsyncSession, user: User, story_id: str) -> dict:
    """(Re-)embed all chapters, character profiles, and scene cards for a story.

    Embeds via llm_service.embed so house-paid embedding cost is metered (BYOK
    runs on the user's own embedder)."""
    client = _get_client()
    if client is None:
        return {"indexed": 0, "reason": "qdrant_unavailable"}

    chapters = (await db.execute(select(Chapter).where(Chapter.story_id == story_id))).scalars().all()
    characters = (await db.execute(select(Character).where(Character.story_id == story_id))).scalars().all()
    scenes = (await db.execute(select(SceneCard).where(SceneCard.story_id == story_id))).scalars().all()

    texts: list[str] = []
    payloads: list[dict] = []
    ids: list[str] = []
    for ch in chapters:
        for idx, chunk in enumerate(_chunk_text(ch.content)):
            texts.append(chunk)
            payloads.append({"kind": "chapter", "chapter_id": ch.id, "chunk_idx": idx, "title": ch.title, "number": ch.number})
            ids.append(_point_id(story_id, "chapter", ch.id, idx))
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
            ids.append(_point_id(story_id, "character", c.id, 0))
    for sc in scenes:
        scene_text = _scene_text(sc)
        if scene_text:
            texts.append(scene_text)
            payloads.append({"kind": "scene", "scene_id": sc.id, "chapter_id": sc.chapter_id, "ordinal": sc.ordinal, "title": sc.title})
            ids.append(_point_id(story_id, "scene", sc.id, 0))

    if not texts:
        # Nothing to index — clear this story's shared points AND retire its legacy
        # collection. Without the legacy drop, a later search() would fall back to
        # the old per-story collection and serve now-deleted content as current.
        await _delete_story_points(client, story_id)
        await _drop_legacy_collection(client, story_id)
        return {"indexed": 0, "reason": "empty"}

    try:
        from app.services import llm_service
        vectors = await llm_service.embed(db, user, texts, story_id=story_id)
    except Exception as e:
        log.warning("embed failed: %s", e)
        return {"indexed": 0, "reason": f"embed_failed:{e}"}
    if not vectors:
        return {"indexed": 0, "reason": "no_vectors"}

    dim = len(vectors[0])
    try:
        if not await ensure_collection(client, COLLECTION, dim):
            return {"indexed": 0, "reason": "dim_mismatch"}
        # Replace this story's slice atomically-ish: drop its points, then upsert.
        await _delete_story_points(client, story_id)
        from qdrant_client.http.models import PointStruct

        points = [
            PointStruct(id=ids[i], vector=vec, payload={"text": texts[i], "story_id": story_id, **payloads[i]})
            for i, vec in enumerate(vectors)
        ]
        await client.upsert(collection_name=COLLECTION, points=points)
        await _drop_legacy_collection(client, story_id)
        return {"indexed": len(points)}
    except Exception as e:
        log.warning("qdrant upsert failed: %s", e)
        return {"indexed": 0, "reason": str(e)}


async def _collection_exists(client, name: str) -> bool:
    try:
        return name in {c.name for c in (await client.get_collections()).collections}
    except Exception:
        return False


async def _search_legacy(client, story_id: str, query_vector: list[float], top_k: int) -> list[dict]:
    """Query the OLD per-story collection, if it still exists (zero-downtime migration).

    A story indexed before M7 lives in `story_{id}_chunks` and isn't in the shared
    collection until its next reindex. We serve from the legacy collection in the
    meantime; reindex migrates it into `gink_chunks` and drops the legacy one.
    """
    legacy = f"story_{story_id}_chunks"
    try:
        resp = await client.query_points(
            collection_name=legacy, query=query_vector, limit=top_k, with_payload=True
        )
        return [{"score": p.score, **(p.payload or {})} for p in resp.points]
    except Exception as e:  # collection-not-found (already migrated) or other — treat as no hits
        log.debug("qdrant legacy search miss: %s", e)
        return []


async def search(story_id: str, query_vector: list[float], *, top_k: int = 8) -> list[dict]:
    client = _get_client()
    if client is None:
        return []
    from qdrant_client.http.models import FieldCondition, Filter, MatchValue

    try:
        # Single shared collection — partition by story_id payload filter.
        # `query_points` is the current API (`search()` was removed in qdrant-client 1.12+).
        resp = await client.query_points(
            collection_name=COLLECTION,
            query=query_vector,
            query_filter=Filter(must=[FieldCondition(key="story_id", match=MatchValue(value=story_id))]),
            limit=top_k,
            with_payload=True,
        )
    except Exception as e:
        # The shared query errored. Only serve legacy data when the shared collection
        # genuinely doesn't exist yet (pre-migration) — NOT on a transient error
        # against an existing collection, which must not be masked with stale chunks.
        if await _collection_exists(client, COLLECTION):
            log.debug("qdrant shared search errored (not serving stale legacy): %s", e)
            return []
        return await _search_legacy(client, story_id, query_vector, top_k)

    hits = [{"score": p.score, **(p.payload or {})} for p in resp.points]
    if hits:
        return hits
    # Shared collection exists but holds nothing for this story yet — fall back to
    # the pre-M7 per-story collection until its next reindex migrates it.
    return await _search_legacy(client, story_id, query_vector, top_k)


async def close_client() -> None:
    """Close the cached Qdrant client (called on app shutdown)."""
    global _client
    if _client is not None:
        try:
            await _client.close()
        finally:
            _client = None
