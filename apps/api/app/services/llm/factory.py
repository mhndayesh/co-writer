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

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import decrypt_secret
from app.db.models import User, UserLLMSettings
from app.services.llm.anthropic_provider import AnthropicProvider
from app.services.llm.base import LLMProvider
from app.services.llm.fallback import FallbackProvider
from app.services.llm.openai_compatible import OpenAICompatibleProvider
from app.services.llm.presets import EMBED_CAPABLE, get_preset
from app.services.llm.roles import category_for_page


async def get_user_settings(db: AsyncSession, user: User) -> UserLLMSettings | None:
    return await db.get(UserLLMSettings, user.id)


def build_provider(
    provider: str,
    *,
    base_url: str = "",
    model: str = "",
    embed_model: str = "",
    api_key: str = "",
) -> LLMProvider:
    """Construct a provider from a preset name + per-lane overrides.

    Falls back to global env defaults (config.py) for blanks, then to the
    deterministic FallbackProvider for an unknown preset.
    """
    preset = get_preset(provider)
    if preset is None:
        return FallbackProvider()

    defaults = provider_defaults(provider)
    env_key = defaults["api_key"]

    if preset.transport == "anthropic":
        # Anthropic can't embed → give it a local LM Studio embed fallback.
        embed_fallback = build_provider("lmstudio")
        return AnthropicProvider(
            api_key=api_key or env_key,
            model=model or defaults["model"],
            fallback_embed_provider=embed_fallback,
        )

    return OpenAICompatibleProvider(
        preset,
        base_url=base_url or defaults["base_url"],
        model=model or defaults["model"],
        embed_model=embed_model or defaults["embed_model"],
        api_key=api_key or env_key,
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


def _lane_provider(lanes: dict | None, lane: str) -> LLMProvider:
    """Build the provider for a lane from the stored JSON, or env default."""
    cfg = (lanes or {}).get(lane) or {}
    provider = cfg.get("provider") or get_settings().llm_provider
    return build_provider(
        provider,
        base_url=cfg.get("base_url", ""),
        model=cfg.get("model", ""),
        embed_model=cfg.get("embed_model", ""),
        api_key=decrypt_secret(cfg.get("api_key_ciphertext", "")),
    )


async def get_provider_for_page(db: AsyncSession, user: User, page: str) -> LLMProvider:
    """Resolve the provider for a task `page` via its category lane."""
    row = await get_user_settings(db, user)
    lanes = row.lanes if row else None
    lane = category_for_page(page)  # "creative" | "technical"
    return _lane_provider(lanes, lane)


async def get_embedding_provider(db: AsyncSession, user: User) -> LLMProvider:
    """Resolve the embedding provider. Must be embed-capable — if the embedding
    lane points at a non-embedding preset, fall back to local LM Studio."""
    row = await get_user_settings(db, user)
    lanes = row.lanes if row else None
    cfg = (lanes or {}).get("embedding") or {}
    provider = cfg.get("provider") or "lmstudio"
    if provider in EMBED_CAPABLE:
        return _lane_provider(lanes, "embedding")
    return build_provider("lmstudio")  # safe local embedder


async def get_provider_for_user(db: AsyncSession, user: User) -> LLMProvider:
    """Back-compat alias → the creative lane (used where no page is carried)."""
    row = await get_user_settings(db, user)
    return _lane_provider(row.lanes if row else None, "creative")
