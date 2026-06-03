"""LLM Router — resolve which provider handles a task.

Three lanes: creative / technical / embedding. Each lane is one (preset, model,
key) config stored in `user_llm_settings.lanes` (JSON). A task's `page` maps to
a category (creative|technical) via roles.py; embeddings use the embedding lane.

No mode enum, no per-task profile rows — "use one model for everything" is a
frontend convenience that writes the same config into all three lanes.

The module keeps the name `factory` so existing imports keep working; the public
functions are the router.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ByokKeyMissing
from app.core.ssrf import validate_provider_base_url
from app.core.security import decrypt_secret
from app.db.models import User, UserLLMSettings
from app.services.llm.anthropic_provider import AnthropicProvider
from app.services.llm.base import LLMProvider
from app.services.llm.fallback import FallbackProvider
from app.services.llm.openai_compatible import OpenAICompatibleProvider
from app.services.llm.presets import EMBED_CAPABLE, get_preset
from app.services.llm.roles import category_for_page

if TYPE_CHECKING:
    from app.services.site_config_service import SiteConfig


async def get_user_settings(db: AsyncSession, user: User) -> UserLLMSettings | None:
    return await db.get(UserLLMSettings, user.id)


def build_provider(
    provider: str,
    *,
    base_url: str = "",
    model: str = "",
    embed_model: str = "",
    api_key: str = "",
    env_key_fallback: bool = True,
) -> LLMProvider:
    """Construct a provider from a preset name + per-lane overrides.

    Falls back to global env defaults (config.py) for blanks, then to the
    deterministic FallbackProvider for an unknown preset.

    `env_key_fallback` is the BYOK guard: when False, the server's house API key
    is NOT used as a fallback, and a key-requiring provider with no key raises
    ByokKeyMissing. (BYOK subscribers must use their own key — never ours.)
    """
    preset = get_preset(provider)
    if preset is None:
        return FallbackProvider()

    defaults = provider_defaults(provider)
    env_key = defaults["api_key"] if env_key_fallback else ""
    resolved_key = api_key or env_key

    # BYOK with a key-requiring provider but no user key → tell them to add one.
    if not env_key_fallback and preset.auth != "none" and not resolved_key:
        raise ByokKeyMissing(f"Add your {provider} API key in Settings to use AI.")

    # Validate a user-supplied base_url at build time. This is necessary but NOT
    # sufficient against DNS-rebinding (httpx re-resolves at connect time), so the
    # provider also re-checks before every outbound call when the URL is user-set
    # (revalidate_base_url below).
    user_supplied_url = bool(base_url)
    effective_base_url = base_url or defaults["base_url"]
    if user_supplied_url:  # only validate user-supplied overrides (presets are trusted)
        validate_provider_base_url(effective_base_url)

    if preset.transport == "anthropic":
        # Anthropic can't embed → give it a local LM Studio embed fallback.
        embed_fallback = build_provider("lmstudio")
        return AnthropicProvider(
            api_key=resolved_key,
            model=model or defaults["model"],
            fallback_embed_provider=embed_fallback,
        )

    return OpenAICompatibleProvider(
        preset,
        base_url=effective_base_url,
        model=model or defaults["model"],
        embed_model=embed_model or defaults["embed_model"],
        api_key=resolved_key,
        revalidate_base_url=user_supplied_url,
    )


def provider_defaults(provider: str) -> dict[str, str]:
    """Resolved defaults for a preset, honoring env overrides from config.py."""
    s = get_settings()
    preset = get_preset(provider)
    static = {
        "base_url": preset.base_url if preset else "",
        "model": preset.default_model if preset else "",
        "embed_model": preset.default_embed_model if preset else "",
        "api_key": "",
    }
    env_defaults = {
        "lmstudio": {
            "base_url": s.lmstudio_base_url,
            "model": s.lmstudio_model,
            "embed_model": s.lmstudio_embed_model,
            "api_key": "",
        },
        "openai": {
            "base_url": s.openai_base_url,
            "model": s.openai_model,
            "embed_model": s.openai_embed_model,
            "api_key": s.openai_api_key,
        },
        "openrouter": {
            "base_url": s.openrouter_base_url,
            "model": s.openrouter_model,
            "embed_model": "",
            "api_key": s.openrouter_api_key,
        },
        "gemini": {
            "base_url": s.gemini_base_url,
            "model": s.gemini_model,
            "embed_model": s.gemini_embed_model,
            "api_key": s.gemini_api_key,
        },
        "anthropic": {
            "base_url": "",
            "model": s.anthropic_model,
            "embed_model": "",
            "api_key": s.anthropic_api_key,
        },
    }.get(provider, {})
    return {**static, **{k: v for k, v in env_defaults.items() if v}}


def default_lane_config(provider: str | None = None) -> dict[str, str]:
    provider = provider or get_settings().llm_provider
    defaults = provider_defaults(provider)
    return {
        "provider": provider,
        "base_url": defaults["base_url"],
        "model": defaults["model"],
        "embed_model": defaults["embed_model"],
        "api_key_ciphertext": "",
    }


def _lane_provider(lanes: dict | None, lane: str, *, env_key_fallback: bool = True) -> LLMProvider:
    """Build the provider for a user lane from the stored JSON, or env default."""
    cfg = (lanes or {}).get(lane) or {}
    provider = cfg.get("provider") or get_settings().llm_provider
    return build_provider(
        provider,
        base_url=cfg.get("base_url", ""),
        model=cfg.get("model", ""),
        embed_model=cfg.get("embed_model", ""),
        api_key=decrypt_secret(cfg.get("api_key_ciphertext", "")),
        env_key_fallback=env_key_fallback,
    )


# ── House ("dev AI") providers — paid for by the website, used by free + dev_ai ──
# The owner sets the house default in the UI (stored in site_settings, passed in
# as `config`); a blank/None config falls back to the env default (system_llm_provider).

def house_provider_for_page(page: str, config: "SiteConfig | None" = None) -> LLMProvider:
    """The house chat provider (server key). Free trial + dev_ai run on this, and
    so does the owner while shape-shifted into a house tier. Owner-configured DB
    default wins; otherwise the env default."""
    s = get_settings()
    provider = (config.house_provider if (config and config.house_provider) else (s.system_llm_provider or s.llm_provider))
    return build_provider(
        provider,
        base_url=(config.house_base_url if config else ""),
        model=(config.house_model if config else ""),
        embed_model=(config.house_embed_model if config else ""),
        api_key=(config.house_api_key if config else ""),
        env_key_fallback=True,  # house path: env key is the fallback when DB key blank
    )


def house_embedding_provider(config: "SiteConfig | None" = None) -> LLMProvider:
    s = get_settings()
    provider = (config.house_provider if (config and config.house_provider) else (s.system_llm_provider or s.llm_provider))
    if provider in EMBED_CAPABLE:
        return build_provider(
            provider,
            base_url=(config.house_base_url if config else ""),
            model=(config.house_model if config else ""),
            embed_model=(config.house_embed_model if config else ""),
            api_key=(config.house_api_key if config else ""),
            env_key_fallback=True,
        )
    return build_provider("lmstudio")  # safe local embedder


# Back-compat aliases (env-only) — no remaining callers, kept for any external import.
def system_provider_for_page(page: str) -> LLMProvider:
    return house_provider_for_page(page, None)


def system_embedding_provider() -> LLMProvider:
    return house_embedding_provider(None)


async def get_provider_for_page(
    db: AsyncSession, user: User, page: str, *, key_source: str | None = None
) -> LLMProvider:
    """Resolve the provider for a task `page`.

    Branches on the EFFECTIVE entitlement (which already accounts for the owner's
    shape-shift), not raw owner-ness:
      - own-lane tiers (real BYOK, real owner, or owner-acting-as-byok) → the
        user's configured lane. Real BYOK with no key raises ByokKeyMissing; the
        owner instead falls back to the house default.
      - house tiers (free, dev_ai, or owner-acting-as-free/dev_ai) → the owner's
        configured house default (DB, env fallback).
    """
    from app.services import entitlement_service, site_config_service

    config = await site_config_service.get_site_config(db)
    ent = entitlement_service.get_entitlement(user, config)
    eff_ks = key_source if key_source is not None else ent.key_source

    row = await get_user_settings(db, user)
    lanes = row.lanes if row else None
    lane = category_for_page(page)  # "creative" | "technical"

    own_lane = eff_ks == "user" or ent.effective_tier == entitlement_service.OWNER_TIER
    if own_lane:
        try:
            return _lane_provider(lanes, lane, env_key_fallback=False)
        except ByokKeyMissing:
            if ent.effective_tier == entitlement_service.OWNER_TIER:
                return house_provider_for_page(page, config)  # owner: degrade, don't error
            raise  # real BYOK without a key must surface the error
    return house_provider_for_page(page, config)  # house tiers → owner's house default


async def get_embedding_provider_with_source(
    db: AsyncSession, user: User, *, key_source: str | None = None
) -> tuple[LLMProvider, str]:
    """Resolve the embedding provider AND who pays for it. Embeddings are
    best-effort, so a missing BYOK key degrades to the local LM Studio embedder
    rather than erroring.

    - own-lane tiers (BYOK, real owner, owner-acting-as-byok) → their embedding
      lane. key_source="user" when it uses their key; "none" when it degrades to
      the free local embedder.
    - house tiers (free, dev_ai) → the owner's house embedder. key_source="server"
      when that's a real remote (house-paid) provider — so [`llm_service.embed`]
      meters it; "none" when the house embedder is local LM Studio (free).

    The returned key_source is what makes house embedding cost show up on the
    llm_runs ledger and count against the plan (BYOK pays their own provider)."""
    from app.services import entitlement_service, site_config_service

    config = await site_config_service.get_site_config(db)
    ent = entitlement_service.get_entitlement(user, config)
    eff_ks = key_source if key_source is not None else ent.key_source

    row = await get_user_settings(db, user)
    lanes = row.lanes if row else None
    cfg = (lanes or {}).get("embedding") or {}
    provider = cfg.get("provider") or "lmstudio"

    own_lane = eff_ks == "user" or ent.effective_tier == entitlement_service.OWNER_TIER
    if own_lane:
        if provider in EMBED_CAPABLE:
            try:
                return _lane_provider(lanes, "embedding", env_key_fallback=False), "user"
            except ByokKeyMissing:
                return build_provider("lmstudio"), "none"
        return build_provider("lmstudio"), "none"  # lane can't embed → local fallback

    prov = house_embedding_provider(config)  # house tiers → owner's house embedder
    # Local LM Studio is free; any real remote house provider is house-paid → meter.
    return prov, ("none" if prov.name == "lmstudio" else "server")


async def get_embedding_provider(
    db: AsyncSession, user: User, *, key_source: str | None = None
) -> LLMProvider:
    """Back-compat: the provider only. Prefer get_embedding_provider_with_source
    (or llm_service.embed) on cost-bearing paths so house usage gets metered."""
    prov, _ = await get_embedding_provider_with_source(db, user, key_source=key_source)
    return prov


async def get_provider_for_user(db: AsyncSession, user: User) -> LLMProvider:
    """Back-compat alias → the creative lane (used where no page is carried)."""
    return await get_provider_for_page(db, user, "flow.polish")
