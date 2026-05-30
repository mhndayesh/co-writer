from fastapi import APIRouter
from sqlalchemy import select

from app.core.deps import CurrentUser, DB, get_user_story
from app.core.errors import NotFound, envelope_ok
from app.db.models import Faction
from app.db.schemas import FactionIn, FactionOut

router = APIRouter()


@router.get("/{story_id}/factions")
async def list_factions(story_id: str, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    rows = (await db.execute(select(Faction).where(Faction.story_id == story_id))).scalars().all()
    return envelope_ok({"factions": [FactionOut.model_validate(r).model_dump() for r in rows]})


@router.post("/{story_id}/factions")
async def create_faction(story_id: str, payload: FactionIn, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    row = Faction(story_id=story_id, **payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return envelope_ok({"faction": FactionOut.model_validate(row).model_dump()})


@router.patch("/{story_id}/factions/{faction_id}")
async def patch_faction(story_id: str, faction_id: str, payload: FactionIn, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    row = await db.get(Faction, faction_id)
    if row is None or row.story_id != story_id:
        raise NotFound("Faction not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await db.commit()
    await db.refresh(row)
    return envelope_ok({"faction": FactionOut.model_validate(row).model_dump()})


@router.delete("/{story_id}/factions/{faction_id}")
async def delete_faction(story_id: str, faction_id: str, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    row = await db.get(Faction, faction_id)
    if row is None or row.story_id != story_id:
        raise NotFound("Faction not found")
    await db.delete(row)
    await db.commit()
    return envelope_ok({"deleted": faction_id})
