"""Admin tools — manual plan management & usage inspection.

Access is granted to users with `is_admin=True` OR whose email is listed in the
ADMIN_EMAILS env var (so the first admin can be bootstrapped without a DB edit).
This is also how plans get assigned while there is no live payment provider.
"""
from fastapi import APIRouter

from app.core.config import get_settings
from app.core.deps import CurrentUser, DB
from app.core.errors import Forbidden, NotFound, envelope_ok
from app.core.security import encrypt_secret
from app.db.models import SiteSettings, User
from app.db.schemas import ActAsRequest, CreateCodeRequest, SetPlanRequest, SiteConfigIn, UserOut
from app.services import billing_service, entitlement_service, redemption_service, site_config_service

router = APIRouter()


def _require_admin(user: User) -> None:
    # Same owner/admin check that grants unlimited AI (is_admin or ADMIN_EMAILS).
    if not entitlement_service.is_owner(user):
        raise Forbidden("Admin access required")


def _site_config_out(row: SiteSettings | None) -> dict:
    """Owner-facing view of site config — never leaks the stored key, and includes
    the env defaults so the UI can show them as placeholders for blank caps."""
    s = get_settings()
    return {
        "house": {
            "provider": (row.house_provider if row else None),
            "base_url": (row.house_base_url if row else ""),
            "model": (row.house_model if row else ""),
            "embed_model": (row.house_embed_model if row else ""),
            "has_api_key": bool(row and row.house_api_key_ciphertext),
        },
        "caps": {
            "dev_ai_max_actions": (row.dev_ai_max_actions if row else None),
            "dev_ai_max_tokens": (row.dev_ai_max_tokens if row else None),
            "free_trial_max_actions": (row.free_trial_max_actions if row else None),
            "free_trial_max_tokens": (row.free_trial_max_tokens if row else None),
        },
        "defaults": {  # env fallbacks shown when a cap is left blank
            "dev_ai_max_actions": s.dev_ai_max_actions_per_month,
            "dev_ai_max_tokens": s.dev_ai_max_tokens_per_month,
            "free_trial_max_actions": s.free_trial_max_actions,
            "free_trial_max_tokens": s.free_trial_max_tokens,
            "env_house_provider": (s.system_llm_provider or s.llm_provider),
        },
    }


@router.post("/users/{user_id}/plan")
async def set_user_plan(user_id: str, payload: SetPlanRequest, user: CurrentUser, db: DB):
    _require_admin(user)
    target = await db.get(User, user_id)
    if target is None:
        raise NotFound("User not found")
    await billing_service.set_plan(db, target, payload.tier, status=payload.status)
    await db.commit()
    await db.refresh(target)
    return envelope_ok({"user": UserOut.model_validate(target).model_dump(mode="json")})


@router.get("/users/{user_id}/usage")
async def user_usage(user_id: str, user: CurrentUser, db: DB):
    _require_admin(user)
    target = await db.get(User, user_id)
    if target is None:
        raise NotFound("User not found")
    return envelope_ok(await entitlement_service.usage_summary(db, target))


@router.post("/users/{user_id}/logout")
async def force_logout(user_id: str, user: CurrentUser, db: DB):
    """Force-logout a user across BOTH auth paths (e.g. a compromised session):
    bump token_version (instantly invalidates every legacy HS256 token) and revoke
    their active Clerk sessions server-side via the Clerk Backend API."""
    _require_admin(user)
    target = await db.get(User, user_id)
    if target is None:
        raise NotFound("User not found")

    target.token_version = (target.token_version or 0) + 1
    await db.commit()

    revoked = 0
    if target.clerk_user_id:
        from app.services import clerk_service
        revoked = await clerk_service.revoke_user_sessions(target.clerk_user_id)

    return envelope_ok({
        "user_id": user_id,
        "legacy_tokens_invalidated": True,
        "clerk_sessions_revoked": revoked,
    })


# ── Redemption (promo / gift) codes ───────────────────────────────────────────

@router.post("/codes")
async def create_code(payload: CreateCodeRequest, user: CurrentUser, db: DB):
    """Mint a code that grants `tier` for `duration_days` (null = lifetime) when
    redeemed, up to `max_uses` times (null = unlimited). Blank `code` → auto-generate."""
    _require_admin(user)
    code = await redemption_service.create_code(
        db, user, tier=payload.tier, duration_days=payload.duration_days,
        max_uses=payload.max_uses, note=payload.note, code=payload.code,
    )
    await db.commit()
    return envelope_ok(redemption_service.serialize(code))


@router.get("/codes")
async def list_codes(user: CurrentUser, db: DB):
    _require_admin(user)
    return envelope_ok({"codes": await redemption_service.list_codes(db)})


@router.post("/codes/{code_id}/deactivate")
async def deactivate_code(code_id: str, user: CurrentUser, db: DB):
    _require_admin(user)
    await redemption_service.deactivate_code(db, code_id)
    await db.commit()
    return envelope_ok({"deactivated": code_id})


# ── Shape-shift: owner "view as" tier ─────────────────────────────────────────

@router.put("/act-as")
async def set_act_as(payload: ActAsRequest, user: CurrentUser, db: DB):
    """Owner-only: simulate a tier so you can test the real per-tier experience.
    None or "owner" exits test mode. Returns the (now simulated) usage summary."""
    _require_admin(user)
    tier = payload.tier
    user.act_as_tier = None if tier in (None, "", "owner") else tier
    await db.commit()
    await db.refresh(user)
    return envelope_ok(await entitlement_service.usage_summary(db, user))


@router.delete("/act-as")
async def clear_act_as(user: CurrentUser, db: DB):
    """Owner-only convenience: exit test mode (clear act_as_tier)."""
    _require_admin(user)
    user.act_as_tier = None
    await db.commit()
    await db.refresh(user)
    return envelope_ok(await entitlement_service.usage_summary(db, user))


# ── House default AI + tunable caps ───────────────────────────────────────────

@router.get("/site-config")
async def get_site_config(user: CurrentUser, db: DB):
    _require_admin(user)
    row = await db.get(SiteSettings, "singleton")
    return envelope_ok(_site_config_out(row))


@router.put("/site-config")
async def put_site_config(payload: SiteConfigIn, user: CurrentUser, db: DB):
    """Owner-only: set the house default AI (what free + dev_ai users run on) and
    the tunable usage caps. A blank api_key keeps the stored one; blank caps fall
    back to env."""
    _require_admin(user)
    row = await db.get(SiteSettings, "singleton")
    if row is None:
        row = SiteSettings(id="singleton")
        db.add(row)

    h = payload.house
    row.house_provider = h.provider
    row.house_base_url = h.base_url
    row.house_model = h.model
    row.house_embed_model = h.embed_model
    if h.api_key:  # blank preserves the existing ciphertext
        row.house_api_key_ciphertext = encrypt_secret(h.api_key)

    c = payload.caps
    row.dev_ai_max_actions = c.dev_ai_max_actions
    row.dev_ai_max_tokens = c.dev_ai_max_tokens
    row.free_trial_max_actions = c.free_trial_max_actions
    row.free_trial_max_tokens = c.free_trial_max_tokens

    await db.commit()
    await db.refresh(row)
    site_config_service.invalidate()  # drop the cache so the change is live now
    return envelope_ok(_site_config_out(row))
