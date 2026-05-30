from fastapi import APIRouter

from app.core.deps import CurrentUser, DB, get_user_story
from app.core.errors import envelope_ok
from app.db.models import World
from app.db.schemas import WorldIn, WorldOut

router = APIRouter()


@router.get("/{story_id}/world")
async def get_world(story_id: str, user: CurrentUser, db: DB):
    story = await get_user_story(story_id, user, db)
    world = await db.get(World, story.id)
    if world is None:
        world = World(story_id=story.id)
        db.add(world)
        await db.commit()
        await db.refresh(world)
    return envelope_ok({"world": WorldOut.model_validate(world).model_dump()})


@router.patch("/{story_id}/world")
async def patch_world(story_id: str, payload: WorldIn, user: CurrentUser, db: DB):
    story = await get_user_story(story_id, user, db)
    world = await db.get(World, story.id)
    if world is None:
        world = World(story_id=story.id)
        db.add(world)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(world, field, value)
    await db.commit()
    await db.refresh(world)
    return envelope_ok({"world": WorldOut.model_validate(world).model_dump()})
