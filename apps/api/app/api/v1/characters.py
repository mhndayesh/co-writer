from fastapi import APIRouter, Query
from sqlalchemy import select

from app.core.deps import CurrentUser, DB, get_user_story
from app.core.errors import NotFound, envelope_ok
from app.db.models import Character, CharacterRelationship
from app.db.schemas import CharacterIn, CharacterOut, CharacterPatch, RelationshipIn, RelationshipOut

router = APIRouter()


@router.get("/{story_id}/characters")
async def list_characters(
    story_id: str,
    user: CurrentUser,
    db: DB,
    limit: int | None = Query(None, ge=1, le=500, description="Opt-in page size; omit to return all."),
    offset: int = Query(0, ge=0),
):
    await get_user_story(story_id, user, db)
    stmt = select(Character).where(Character.story_id == story_id).order_by(Character.created_at)
    if limit is not None:
        stmt = stmt.offset(offset).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return envelope_ok({"characters": [CharacterOut.model_validate(c).model_dump() for c in rows]})


@router.post("/{story_id}/characters")
async def create_character(story_id: str, payload: CharacterIn, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    ch = Character(story_id=story_id, **payload.model_dump())
    db.add(ch)
    await db.commit()
    await db.refresh(ch)
    return envelope_ok({"character": CharacterOut.model_validate(ch).model_dump()})


@router.patch("/{story_id}/characters/{character_id}")
async def patch_character(story_id: str, character_id: str, payload: CharacterPatch, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    ch = await db.get(Character, character_id)
    if ch is None or ch.story_id != story_id:
        raise NotFound("Character not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(ch, field, value)
    await db.commit()
    await db.refresh(ch)
    return envelope_ok({"character": CharacterOut.model_validate(ch).model_dump()})


@router.delete("/{story_id}/characters/{character_id}")
async def delete_character(story_id: str, character_id: str, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    ch = await db.get(Character, character_id)
    if ch is None or ch.story_id != story_id:
        raise NotFound("Character not found")
    await db.delete(ch)
    await db.commit()
    return envelope_ok({"deleted": character_id})


@router.get("/{story_id}/characters/{character_id}/relationships")
async def list_relationships(story_id: str, character_id: str, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    rows = (await db.execute(
        select(CharacterRelationship).where(
            CharacterRelationship.story_id == story_id,
            CharacterRelationship.source_id == character_id,
        )
    )).scalars().all()
    return envelope_ok({"relationships": [RelationshipOut.model_validate(r).model_dump() for r in rows]})


@router.post("/{story_id}/characters/{character_id}/relationships")
async def add_relationship(story_id: str, character_id: str, payload: RelationshipIn, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    # Upsert on the (story, source, target) invariant — re-posting an existing edge
    # updates it in place instead of tripping the unique constraint, mirroring how
    # Flow approve() reconciles relationships.
    rel = (await db.execute(
        select(CharacterRelationship).where(
            CharacterRelationship.story_id == story_id,
            CharacterRelationship.source_id == character_id,
            CharacterRelationship.target_id == payload.target_id,
        )
    )).scalar_one_or_none()
    if rel is None:
        rel = CharacterRelationship(
            story_id=story_id,
            source_id=character_id,
            target_id=payload.target_id,
            type=payload.type,
            description=payload.description,
        )
        db.add(rel)
    else:
        rel.type = payload.type
        rel.description = payload.description
    await db.commit()
    await db.refresh(rel)
    return envelope_ok({"relationship": RelationshipOut.model_validate(rel).model_dump()})


@router.delete("/{story_id}/relationships/{relationship_id}")
async def delete_relationship(story_id: str, relationship_id: str, user: CurrentUser, db: DB):
    await get_user_story(story_id, user, db)
    rel = await db.get(CharacterRelationship, relationship_id)
    if rel is None or rel.story_id != story_id:
        raise NotFound("Relationship not found")
    await db.delete(rel)
    await db.commit()
    return envelope_ok({"deleted": relationship_id})
