"""Subscription tiers, entitlement metering, and BYOK key enforcement."""
import pytest

from app.core import plans
from app.core.errors import ByokKeyMissing
from app.core.security import encrypt_secret
from app.db.models import LLMRun, SiteSettings, User, UserLLMSettings
from app.db.session import SessionLocal
from app.services import billing_service, entitlement_service, site_config_service
from app.services.llm.factory import get_provider_for_page


async def _mk_user(db, email: str, tier="free", status=plans.STATUS_NONE) -> User:
    u = User(email=email, password_hash="x", display_name="t", plan_tier=tier, plan_status=status)
    db.add(u)
    await db.flush()
    return u


async def _set_lane(db, user: User, provider: str, *, key: str, lane="creative"):
    ciphertext = encrypt_secret(key) if key else ""
    row = UserLLMSettings(user_id=user.id, lanes={
        lane: {"provider": provider, "base_url": "", "model": "", "embed_model": "", "api_key_ciphertext": ciphertext}
    })
    db.add(row)
    await db.flush()


async def _log_server_runs(db, user: User, n: int, tokens_each: int = 0):
    for i in range(n):
        db.add(LLMRun(
            user_id=user.id, provider="openai", model="m", page="flow.polish",
            tokens_in=tokens_each, tokens_out=0, key_source="server",
        ))
    await db.flush()


# ── key-source routing per tier ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_free_user_routes_to_house_provider_ignoring_lanes():
    async with SessionLocal() as db:
        u = await _mk_user(db, "free@test.com", tier="free")
        # Even with an OpenAI lane configured, a free user runs on the house model.
        await _set_lane(db, u, "openai", key="their-key")
        prov = await get_provider_for_page(db, u, "flow.polish")
        assert prov.name == "lmstudio"  # default SYSTEM_LLM_PROVIDER


@pytest.mark.asyncio
async def test_owner_uses_configured_lane_not_house_provider():
    # The site owner operates the instance, so a provider they configured in
    # Settings is honored even though their entitlement key_source is "server".
    async with SessionLocal() as db:
        u = await _mk_user(db, "owner@test.com", tier="free")
        u.is_admin = True
        await db.flush()
        await _set_lane(db, u, "openai", key="owner-key")
        prov = await get_provider_for_page(db, u, "flow.polish")
        assert prov.name == "openai"


@pytest.mark.asyncio
async def test_owner_lane_without_required_key_falls_back_to_house():
    # Owner picked a key-requiring provider but left the key blank → house model,
    # not a hard error.
    async with SessionLocal() as db:
        u = await _mk_user(db, "owner2@test.com", tier="free")
        u.is_admin = True
        await db.flush()
        await _set_lane(db, u, "openai", key="")  # no key
        prov = await get_provider_for_page(db, u, "flow.polish")
        assert prov.name == "lmstudio"  # house fallback


@pytest.mark.asyncio
async def test_byok_with_key_uses_own_provider():
    async with SessionLocal() as db:
        u = await _mk_user(db, "byok-ok@test.com", tier=plans.BYOK, status=plans.STATUS_ACTIVE)
        await _set_lane(db, u, "openai", key="their-key")
        prov = await get_provider_for_page(db, u, "flow.polish")
        assert prov.name == "openai"


@pytest.mark.asyncio
async def test_byok_without_key_is_rejected_not_silently_using_server_key():
    async with SessionLocal() as db:
        u = await _mk_user(db, "byok-nokey@test.com", tier=plans.BYOK, status=plans.STATUS_ACTIVE)
        await _set_lane(db, u, "openai", key="")  # no key
        with pytest.raises(ByokKeyMissing):
            await get_provider_for_page(db, u, "flow.polish")


@pytest.mark.asyncio
async def test_lapsed_paid_plan_falls_back_to_free_entitlement():
    async with SessionLocal() as db:
        u = await _mk_user(db, "lapsed@test.com", tier=plans.DEV_AI, status=plans.STATUS_CANCELED)
        ent = entitlement_service.get_entitlement(u)
        assert ent.effective_tier == plans.FREE
        assert ent.key_source == "server"


# ── usage metering / authorization ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_free_trial_blocks_after_action_allowance():
    async with SessionLocal() as db:
        u = await _mk_user(db, "trial@test.com", tier="free")
        cap = plans.plan_limit(plans.FREE).max_actions
        await _log_server_runs(db, u, cap - 1)
        assert (await entitlement_service.authorize_ai(db, u, "flow.polish")).allowed is True
        await _log_server_runs(db, u, 1)  # now at the cap
        auth = await entitlement_service.authorize_ai(db, u, "flow.polish")
        assert auth.allowed is False
        assert auth.reason == "trial_exhausted"


@pytest.mark.asyncio
async def test_dev_ai_blocks_on_token_cap():
    async with SessionLocal() as db:
        u = await _mk_user(db, "devai@test.com", tier=plans.DEV_AI, status=plans.STATUS_ACTIVE)
        cap = plans.plan_limit(plans.DEV_AI).max_tokens
        await _log_server_runs(db, u, 1, tokens_each=cap)  # one fat call hits the token cap
        auth = await entitlement_service.authorize_ai(db, u, "flow.polish")
        assert auth.allowed is False
        assert auth.reason == "quota_exceeded"


@pytest.mark.asyncio
async def test_byok_usage_not_metered():
    async with SessionLocal() as db:
        u = await _mk_user(db, "byok-meter@test.com", tier=plans.BYOK, status=plans.STATUS_ACTIVE)
        # Even with tons of (server-logged) usage, BYOK is never capped on our side.
        await _log_server_runs(db, u, 10_000, tokens_each=10_000)
        auth = await entitlement_service.authorize_ai(db, u, "flow.polish")
        assert auth.allowed is True
        assert auth.key_source == "user"


@pytest.mark.asyncio
async def test_unmetered_diagnostic_always_allowed():
    async with SessionLocal() as db:
        u = await _mk_user(db, "diag@test.com", tier="free")
        await _log_server_runs(db, u, plans.plan_limit(plans.FREE).max_actions + 5)
        # llm.test bypasses the meter so users can still verify connectivity.
        assert (await entitlement_service.authorize_ai(db, u, "llm.test")).allowed is True


# ── billing service ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_set_plan_syncs_user_cache_and_can_downgrade():
    async with SessionLocal() as db:
        u = await _mk_user(db, "billing@test.com", tier="free")
        await billing_service.set_plan(db, u, plans.DEV_AI)
        assert u.plan_tier == plans.DEV_AI
        assert u.plan_status == plans.STATUS_ACTIVE

        await billing_service.set_plan(db, u, plans.FREE)
        assert u.plan_tier == plans.FREE
        assert u.plan_status == plans.STATUS_NONE


# ── HTTP-level: billing endpoints over the real ASGI app ────────────────────

async def _signup(client, email):
    r = await client.post("/v1/auth/signup", json={"email": email, "password": "password123"})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    return data["user"], data["tokens"]["access_token"]


@pytest.mark.asyncio
async def test_billing_flow_over_http(client):
    user, token = await _signup(client, "http-billing@test.com")
    auth = {"Authorization": f"Bearer {token}"}

    # New users start on the free trial.
    assert user["plan_tier"] == "free"

    # Public plan catalog has all three tiers.
    r = await client.get("/v1/billing/plans")
    tiers = {p["tier"] for p in r.json()["data"]["plans"]}
    assert {"free", "dev_ai", "byok"} <= tiers

    # Entitlement starts free + metered.
    me = (await client.get("/v1/billing/me", headers=auth)).json()["data"]
    assert me["effective_tier"] == "free" and me["metered"] is True

    # Manual checkout activates instantly.
    r = await client.post("/v1/billing/checkout", headers=auth, json={"tier": "dev_ai"})
    assert r.json()["data"]["activated"] is True

    me = (await client.get("/v1/billing/me", headers=auth)).json()["data"]
    assert me["effective_tier"] == "dev_ai" and me["key_source"] == "server"


@pytest.mark.asyncio
async def test_owner_email_gets_unlimited_ai():
    # ADMIN_EMAILS is empty by default (no hardcoded owner) — a deployment must
    # set it explicitly, which this test simulates on the cached settings.
    from app.core.config import get_settings
    settings = get_settings()
    prev_admin = settings.admin_emails
    settings.admin_emails = "owner@example.com"
    try:
        async with SessionLocal() as db:
            u = await _mk_user(db, "owner@example.com", tier="free")
            ent = entitlement_service.get_entitlement(u)
            assert ent.effective_tier == "owner"
            # Even far past any cap, the owner is never blocked, and runs on house keys.
            await _log_server_runs(db, u, 9999, tokens_each=9999)
            auth = await entitlement_service.authorize_ai(db, u, "flow.polish")
            assert auth.allowed is True and auth.key_source == "server"
    finally:
        settings.admin_emails = prev_admin


@pytest.mark.asyncio
async def test_is_admin_flag_grants_owner():
    async with SessionLocal() as db:
        u = await _mk_user(db, "flagged-admin@test.com", tier="free")
        u.is_admin = True
        await db.flush()
        assert entitlement_service.get_entitlement(u).effective_tier == "owner"


@pytest.mark.asyncio
async def test_token_stats_counts_all_in_and_out():
    async with SessionLocal() as db:
        u = await _mk_user(db, "tokcount@test.com", tier=plans.BYOK, status=plans.STATUS_ACTIVE)
        # Mix of key sources — token_stats counts them ALL (unlike the plan meter).
        for ks in ("server", "user", "none"):
            db.add(LLMRun(user_id=u.id, provider="p", model="m", page="flow.polish",
                          tokens_in=100, tokens_out=40, key_source=ks))
        await db.flush()
        stats = await entitlement_service.token_stats(db, u)
        assert stats["runs"] == 3
        assert stats["tokens_in"] == 300 and stats["tokens_out"] == 120
        assert stats["total"] == 420
        assert stats["avg_total"] == 140.0


@pytest.mark.asyncio
async def test_admin_requires_admin_rights(client):
    _, token = await _signup(client, "not-admin@test.com")
    auth = {"Authorization": f"Bearer {token}"}
    r = await client.post("/v1/admin/users/whatever/plan", headers=auth, json={"tier": "byok"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"


# ── Owner control panel: shape-shift, DB house default, tunable caps ──────────

async def _set_site_config(db, **fields) -> SiteSettings:
    """Create/replace the singleton site_settings row, then drop the cache so the
    next read reflects it."""
    row = await db.get(SiteSettings, "singleton")
    if row is None:
        row = SiteSettings(id="singleton")
        db.add(row)
    for k, v in fields.items():
        setattr(row, k, v)
    await db.flush()
    site_config_service.invalidate()
    return row


@pytest.mark.asyncio
async def test_caps_apply_only_to_house_key():
    # A DB-tuned free cap blocks the free (house-key) user but never BYOK.
    async with SessionLocal() as db:
        await _set_site_config(db, free_trial_max_actions=1)
        free = await _mk_user(db, "cap-free@test.com", tier="free")
        await _log_server_runs(db, free, 1)
        auth = await entitlement_service.authorize_ai(db, free, "flow.polish")
        assert auth.allowed is False and auth.reason == "trial_exhausted"

        byok = await _mk_user(db, "cap-byok@test.com", tier=plans.BYOK, status=plans.STATUS_ACTIVE)
        await _log_server_runs(db, byok, 50)  # way over any cap
        auth = await entitlement_service.authorize_ai(db, byok, "flow.polish")
        assert auth.allowed is True and auth.key_source == "user"


@pytest.mark.asyncio
async def test_db_caps_override_env():
    async with SessionLocal() as db:
        await _set_site_config(db, dev_ai_max_actions=2)  # env default is 500
        u = await _mk_user(db, "db-cap@test.com", tier=plans.DEV_AI, status=plans.STATUS_ACTIVE)
        cfg = await site_config_service.get_site_config(db)
        assert plans.plan_limit(plans.DEV_AI, cfg).max_actions == 2
        await _log_server_runs(db, u, 2)
        auth = await entitlement_service.authorize_ai(db, u, "flow.polish")
        assert auth.allowed is False and auth.reason == "quota_exceeded"


@pytest.mark.asyncio
async def test_db_house_default_applied():
    # The owner's chosen house provider overrides the env default for house users.
    async with SessionLocal() as db:
        await _set_site_config(db, house_provider="openai")
        free = await _mk_user(db, "house-default@test.com", tier="free")
        prov = await get_provider_for_page(db, free, "flow.polish")
        assert prov.name == "openai"  # not the env default lmstudio


@pytest.mark.asyncio
async def test_act_as_flips_entitlement():
    async with SessionLocal() as db:
        u = await _mk_user(db, "shift-ent@test.com", tier="free")
        u.is_admin = True
        await db.flush()
        cfg = await site_config_service.get_site_config(db)

        u.act_as_tier = "dev_ai"
        ent = entitlement_service.get_entitlement(u, cfg)
        assert ent.effective_tier == "dev_ai" and ent.key_source == "server"

        u.act_as_tier = "byok"
        assert entitlement_service.get_entitlement(u, cfg).key_source == "user"

        u.act_as_tier = None
        assert entitlement_service.get_entitlement(u, cfg).effective_tier == "owner"


@pytest.mark.asyncio
async def test_act_as_flips_provider():
    async with SessionLocal() as db:
        u = await _mk_user(db, "shift-prov@test.com", tier="free")
        u.is_admin = True
        await db.flush()
        await _set_lane(db, u, "openai", key="owner-key")  # personal lane

        u.act_as_tier = "dev_ai"  # house tier → house default (env lmstudio), NOT openai
        await db.flush()
        prov = await get_provider_for_page(db, u, "flow.polish")
        assert prov.name == "lmstudio"

        u.act_as_tier = "byok"  # own-lane tier → personal openai lane
        await db.flush()
        prov = await get_provider_for_page(db, u, "flow.polish")
        assert prov.name == "openai"


@pytest.mark.asyncio
async def test_act_as_flips_caps():
    async with SessionLocal() as db:
        await _set_site_config(db, dev_ai_max_actions=1)
        u = await _mk_user(db, "shift-cap@test.com", tier="free")
        u.is_admin = True
        u.act_as_tier = "dev_ai"
        await db.flush()
        await _log_server_runs(db, u, 1)
        auth = await entitlement_service.authorize_ai(db, u, "flow.polish")
        assert auth.allowed is False and auth.reason == "quota_exceeded"


# ── HTTP-level authorization ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_paid_blocked_from_put_config(client):
    # free/dev_ai (house tiers) cannot save a personal AI lane.
    _, token = await _signup(client, "paid-noconfig@test.com")
    auth = {"Authorization": f"Bearer {token}"}
    r = await client.put("/v1/llm/config", headers=auth, json={"creative": {"provider": "openai"}})
    assert r.status_code == 403

    # A BYOK user may.
    user, token2 = await _signup(client, "byok-config@test.com")
    async with SessionLocal() as db:
        u = await db.get(User, user["id"])
        await billing_service.set_plan(db, u, plans.BYOK, status=plans.STATUS_ACTIVE)
        await db.commit()
    auth2 = {"Authorization": f"Bearer {token2}"}
    r = await client.put("/v1/llm/config", headers=auth2, json={"creative": {"provider": "openai"}})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_act_as_and_site_config_owner_only(client):
    _, token = await _signup(client, "not-owner@test.com")
    auth = {"Authorization": f"Bearer {token}"}
    assert (await client.put("/v1/admin/act-as", headers=auth, json={"tier": "dev_ai"})).status_code == 403
    assert (await client.get("/v1/admin/site-config", headers=auth)).status_code == 403
    assert (await client.put("/v1/admin/site-config", headers=auth, json={"house": {"provider": "openai"}})).status_code == 403
    # And the stray write never persisted an act_as_tier on the non-owner.
    async with SessionLocal() as db:
        from sqlalchemy import select
        u = (await db.execute(select(User).where(User.email == "not-owner@test.com"))).scalar_one()
        assert u.act_as_tier is None
