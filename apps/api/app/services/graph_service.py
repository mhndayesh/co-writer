"""Neo4j knowledge graph projection.

`reproject_story(story_id)` wipes the per-story subgraph and rebuilds it
from the relational data. Story sizes are bounded (hundreds of nodes)
so a full re-projection per save is cheap and avoids drift.

If Neo4j is unreachable, returns a graph derived from Postgres so the
front-end Story Map keeps working.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import (
    Chapter,
    Character,
    CharacterRelationship,
    Faction,
    Location,
    Story,
    Theme,
)
from app.db.schemas import GraphLink, GraphNode, GraphView

log = logging.getLogger("gink.graph")

NODE_KIND_COLOR = {
    "character": "#c89830",
    "chapter": "#b3667a",
    "theme": "#4a7c4e",
    "location": "#5a8aa3",
    "faction": "#7a609a",
}

ALLOWED_NODE_LABELS = {
    "character": "Character",
    "chapter": "Chapter",
    "theme": "Theme",
    "location": "Location",
    "faction": "Faction",
}

RELATIONSHIP_TYPE_MAP = {
    "ally": "ALLIED_WITH",
    "allied": "ALLIED_WITH",
    "enemy": "ENEMY_OF",
    "rival": "RIVAL_OF",
    "family": "FAMILY_OF",
    "lover": "LOVER_OF",
}

_driver = None


def _get_driver():
    """Lazily build the Neo4j driver. Returns None if unconfigured/unreachable."""
    global _driver
    if _driver is not None:
        return _driver
    s = get_settings()
    if not s.neo4j_uri:
        return None
    try:
        from neo4j import AsyncGraphDatabase

        _driver = AsyncGraphDatabase.driver(s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password))
        return _driver
    except Exception as e:
        log.warning("neo4j driver init failed: %s", e)
        return None


async def close_driver() -> None:
    """Close the cached Neo4j driver (called on app shutdown)."""
    global _driver
    if _driver is not None:
        try:
            await _driver.close()
        finally:
            _driver = None


async def reproject_story(db: AsyncSession, story_id: str) -> dict[str, Any]:
    """Re-create the per-story subgraph in Neo4j. No-op if Neo4j unreachable."""
    driver = _get_driver()
    if driver is None:
        return {"projected": False, "reason": "neo4j_unavailable"}

    chars = (await db.execute(select(Character).where(Character.story_id == story_id))).scalars().all()
    rels = (await db.execute(select(CharacterRelationship).where(CharacterRelationship.story_id == story_id))).scalars().all()
    chaps = (await db.execute(select(Chapter).where(Chapter.story_id == story_id).order_by(Chapter.number))).scalars().all()
    locs = (await db.execute(select(Location).where(Location.story_id == story_id))).scalars().all()
    facs = (await db.execute(select(Faction).where(Faction.story_id == story_id))).scalars().all()
    themes = (await db.execute(select(Theme).where(Theme.story_id == story_id))).scalars().all()

    char_rows = [{"id": c.id, "name": c.name, "role": c.role, "status": c.status} for c in chars]
    chap_rows = [
        {"id": c.id, "number": c.number, "title": c.title, "summary": (c.summary or "")[:300],
         "pov": c.pov_character_id, "location": c.location_id, "character_ids": list(c.character_ids or [])}
        for c in chaps
    ]
    loc_rows = [{"id": loc.id, "name": loc.name} for loc in locs]
    fac_rows = [{"id": f.id, "name": f.name} for f in facs]
    theme_rows = [{"id": t.id, "name": t.name} for t in themes]

    rel_rows = []
    for r in rels:
        rel_type = RELATIONSHIP_TYPE_MAP.get(r.type.lower(), "HAS_RELATIONSHIP")
        rel_rows.append({"src": r.source_id, "dst": r.target_id, "type": rel_type, "desc": r.description})

    try:
        async with driver.session() as session:
            # Wipe per-story subgraph
            await session.run("MATCH (n {story_id: $s}) DETACH DELETE n", s=story_id)

            # Create nodes
            await session.run(
                "UNWIND $rows AS r MERGE (c:Character {story_id: $s, id: r.id}) "
                "SET c.name = r.name, c.role = r.role, c.status = r.status",
                rows=char_rows, s=story_id,
            )
            await session.run(
                "UNWIND $rows AS r MERGE (c:Chapter {story_id: $s, id: r.id}) "
                "SET c.number = r.number, c.title = r.title, c.summary = r.summary",
                rows=chap_rows, s=story_id,
            )
            await session.run(
                "UNWIND $rows AS r MERGE (l:Location {story_id: $s, id: r.id}) SET l.name = r.name",
                rows=loc_rows, s=story_id,
            )
            await session.run(
                "UNWIND $rows AS r MERGE (f:Faction {story_id: $s, id: r.id}) SET f.name = r.name",
                rows=fac_rows, s=story_id,
            )
            await session.run(
                "UNWIND $rows AS r MERGE (t:Theme {story_id: $s, id: r.id}) SET t.name = r.name",
                rows=theme_rows, s=story_id,
            )

            # Character-character relationships (dynamic type via APOC if present, else generic)
            for r in rel_rows:
                cypher = (
                    "MATCH (a:Character {story_id: $s, id: $src}), (b:Character {story_id: $s, id: $dst}) "
                    f"MERGE (a)-[rel:{r['type']}]->(b) SET rel.description = $desc"
                )
                await session.run(cypher, s=story_id, src=r["src"], dst=r["dst"], desc=r["desc"])

            # APPEARS_IN edges
            appear_rows = []
            for c in chap_rows:
                for cid in c["character_ids"]:
                    appear_rows.append({"chap_id": c["id"], "char_id": cid})
            if appear_rows:
                await session.run(
                    "UNWIND $rows AS r "
                    "MATCH (c:Character {story_id: $s, id: r.char_id}), (h:Chapter {story_id: $s, id: r.chap_id}) "
                    "MERGE (c)-[:APPEARS_IN]->(h)",
                    rows=appear_rows, s=story_id,
                )

            # OCCURS_IN (chapter → location)
            occurs_rows = [{"chap_id": c["id"], "loc_id": c["location"]} for c in chap_rows if c["location"]]
            if occurs_rows:
                await session.run(
                    "UNWIND $rows AS r "
                    "MATCH (h:Chapter {story_id: $s, id: r.chap_id}), (l:Location {story_id: $s, id: r.loc_id}) "
                    "MERGE (h)-[:OCCURS_IN]->(l)",
                    rows=occurs_rows, s=story_id,
                )

        # Mark story.graph_status + record the successful-sync timestamp so the
        # reconciler knows this story is current. (Callers must commit — approve
        # and reconcile_stale_graphs both do.)
        st = await db.get(Story, story_id)
        if st is not None:
            st.graph_status = "ok"
            st.graph_synced_at = datetime.now(timezone.utc)
        return {"projected": True, "nodes": len(char_rows) + len(chap_rows) + len(loc_rows) + len(fac_rows) + len(theme_rows)}
    except Exception as e:
        log.warning("graph projection failed: %s", e)
        st = await db.get(Story, story_id)
        if st is not None:
            st.graph_status = "unavailable"
        return {"projected": False, "reason": str(e)}


async def reconcile_stale_graphs(limit: int = 25) -> dict[str, Any]:
    """Self-heal stories whose Neo4j projection is missing or stale.

    The projection after Flow approve is best-effort: if Neo4j was down (or the
    process died) the story is left with graph_status != "ok" and Postgres/Neo4j
    drift with nothing to repair it. This sweep — run on a schedule by the ARQ
    worker (see app.workers.export_worker) — retries those stories once Neo4j is
    reachable again, so drift converges back to consistency.

    No-op when Neo4j is unreachable (each reproject short-circuits), so it's safe
    to run on a timer regardless of Neo4j's state. Opens its own DB session.
    """
    driver = _get_driver()
    if driver is None:
        return {"reconciled": 0, "reason": "neo4j_unavailable"}

    from app.db.session import SessionLocal

    healed = 0
    async with SessionLocal() as db:
        stale = (
            await db.execute(
                select(Story.id).where(Story.graph_status != "ok").limit(limit)
            )
        ).scalars().all()
        for sid in stale:
            res = await reproject_story(db, sid)
            if res.get("projected"):
                healed += 1
            else:
                # Neo4j went away mid-sweep — stop; the next run retries the rest.
                break
        await db.commit()
    return {"reconciled": healed, "candidates": len(stale)}


async def get_view(db: AsyncSession, story_id: str) -> GraphView:
    """Return nodes+links for the front-end force graph.

    Reads from Postgres directly — simpler than round-tripping Neo4j for
    visualization, and stays available when Neo4j is down.
    """
    chars = (await db.execute(select(Character).where(Character.story_id == story_id))).scalars().all()
    rels = (await db.execute(select(CharacterRelationship).where(CharacterRelationship.story_id == story_id))).scalars().all()
    chaps = (await db.execute(select(Chapter).where(Chapter.story_id == story_id).order_by(Chapter.number))).scalars().all()
    locs = (await db.execute(select(Location).where(Location.story_id == story_id))).scalars().all()
    facs = (await db.execute(select(Faction).where(Faction.story_id == story_id))).scalars().all()
    themes = (await db.execute(select(Theme).where(Theme.story_id == story_id))).scalars().all()

    nodes: list[GraphNode] = []
    links: list[GraphLink] = []

    for c in chars:
        nodes.append(GraphNode(
            id=f"char:{c.id}", label=c.name, kind="character",
            color=NODE_KIND_COLOR["character"], size=8,
            data={"role": c.role, "status": c.status},
        ))
    for ch in chaps:
        nodes.append(GraphNode(
            id=f"chap:{ch.id}", label=f"Ch{ch.number}. {ch.title or 'Untitled'}", kind="chapter",
            color=NODE_KIND_COLOR["chapter"], size=6,
            data={"number": ch.number, "summary": (ch.summary or "")[:200]},
        ))
    for t in themes:
        nodes.append(GraphNode(
            id=f"theme:{t.id}", label=t.name, kind="theme",
            color=NODE_KIND_COLOR["theme"], size=4,
        ))
    for loc in locs:
        nodes.append(GraphNode(
            id=f"loc:{loc.id}", label=loc.name, kind="location",
            color=NODE_KIND_COLOR["location"], size=5,
        ))
    for f in facs:
        nodes.append(GraphNode(
            id=f"fac:{f.id}", label=f.name, kind="faction",
            color=NODE_KIND_COLOR["faction"], size=5,
        ))

    for r in rels:
        links.append(GraphLink(source=f"char:{r.source_id}", target=f"char:{r.target_id}", kind="relationship", label=r.type))
    for ch in chaps:
        for cid in (ch.character_ids or []):
            links.append(GraphLink(source=f"char:{cid}", target=f"chap:{ch.id}", kind="appears_in"))
        if ch.location_id:
            links.append(GraphLink(source=f"chap:{ch.id}", target=f"loc:{ch.location_id}", kind="occurs_in"))

    # Best-effort report whether neo4j is also up
    driver = _get_driver()
    source: str = "postgres_fallback"
    if driver is not None:
        try:
            async with driver.session() as session:
                await session.run("RETURN 1")
            source = "neo4j"
        except Exception:
            source = "postgres_fallback"

    return GraphView(nodes=nodes, links=links, source=source)


async def subgraph_for_character(story_id: str, character_id: str, hops: int = 1) -> list[str]:
    """Return human-readable lines describing the 1-hop neighborhood of a character.

    Used by RAG. Returns an empty list if Neo4j is unavailable.
    """
    driver = _get_driver()
    if driver is None:
        return []
    try:
        async with driver.session() as session:
            res = await session.run(
                "MATCH (c:Character {story_id: $s, id: $id})-[r]-(n {story_id: $s}) "
                "RETURN c.name AS subj, type(r) AS rel, labels(n)[0] AS kind, "
                "coalesce(n.name, n.title) AS obj LIMIT 40",
                s=story_id, id=character_id,
            )
            lines = []
            async for rec in res:
                lines.append(f"{rec['subj']} {rec['rel']} {rec['kind']}: {rec['obj']}")
            return lines
    except Exception as e:
        log.debug("subgraph query failed: %s", e)
        return []
