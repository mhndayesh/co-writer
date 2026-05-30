from fastapi import APIRouter
from sqlalchemy import select

from app.core.deps import CurrentUser, DB, get_user_story
from app.core.errors import NotFound, envelope_ok
from app.db.models import Location
from app.db.schemas import LocationIn, LocationOut

router = APIRouter()


@router.get("/{story_id}/locations")
async def list_locations(story_id: str, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    rows = (await db.execute(select(Location).where(Location.story_id == story_id))).scalars().all()
    return envelope_ok({"locations": [LocationOut.model_validate(r).model_dump() for r in rows]})


@router.post("/{story_id}/locations")
async def create_location(story_id: str, payload: LocationIn, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    row = Location(story_id=story_id, **payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return envelope_ok({"location": LocationOut.model_validate(row).model_dump()})


@router.patch("/{story_id}/locations/{location_id}")
async def patch_location(story_id: str, location_id: str, payload: LocationIn, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    row = await db.get(Location, location_id)
    if row is None or row.story_id != story_id:
        raise NotFound("Location not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await db.commit()
    await db.refresh(row)
    return envelope_ok({"location": LocationOut.model_validate(row).model_dump()})


@router.delete("/{story_id}/locations/{location_id}")
async def delete_location(story_id: str, location_id: str, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    row = await db.get(Location, location_id)
    if row is None or row.story_id != story_id:
        raise NotFound("Location not found")
    await db.delete(row)
    await db.commit()
    return envelope_ok({"deleted": location_id})
