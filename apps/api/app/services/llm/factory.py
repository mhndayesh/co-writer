"""Resolve the right LLM provider for a user — per task, with 3 routing modes.

Modes (stored on UserLLMSettings.mode):
  single → the user's default profile handles everything (original behavior)
  split  → creative vs technical, routed by the task's category
  custom → a profile per task (task:<page>), falling back to category, then default

The flat columns on UserLLMSettings are the "default" profile. Extra per-role
configs live in the llm_profiles table (role ∈ creative|technical|embedding|task:<page>).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import decrypt_secret
from app.db.models import LLMProfile, User, UserLLMSettings
from app.services.llm.anthropic_provider import AnthropicProvider
from app.services.llm.base import LLMProvider
from app.services.llm.fallback import FallbackProvider
from app.services.llm.gemini_provider import GeminiProvider
from app.services.llm.lmstudio import LMStudioProvider
from app.services.llm.openai_provider import OpenAIProvider
from app.services.llm.openrouter_provider import OpenRouterProvider
from app.services.llm.roles import category_for_page

# Providers that can produce embeddings. Anthropic + OpenRouter can't, so they're
# excluded — get_embedding_provider falls back to a local LM Studio embedder.
EMBED_CAPABLE = ("lmstudio", "openai", "gemini")


async def get_user_settings(db: AsyncSession, user: User) -> UserLLMSettings | None:
    return await db.get(UserLLMSettings, user.id)


async def _get_profile(db: AsyncSession, user: User, role: str) -> LLMProfile | None:
    return (await db.execute(
        select(LLMProfile).where(LLMProfile.user_id == user.id, LLMProfile.role == role)
    )).scalar_one_or_none()


def build_provider(
    provider: str,
    *,
    base_url: str,
    model: str,
    embed_model: str,
    api_key: str,
) -> LLMProvider:
    s = get_settings()
    if provider == "lmstudio":
        return LMStudioProvider(
            base_url=base_url or s.lmstudio_base_url,
            model=model or s.lmstudio_model,
            embed_model=embed_model or s.lmstudio_embed_model,
        )
    if provider == "openai":
        return OpenAIProvider(
            api_key=api_key or s.openai_api_key,
            base_url=base_url or s.openai_base_url,
            model=model or s.openai_model,
            embed_model=embed_model or s.openai_embed_model,
        )
    if provider == "anthropic":
        embed_fallback = LMStudioProvider(
            base_url=s.lmstudio_base_url,
            model=s.lmstudio_model,
            embed_model=s.lmstudio_embed_model,
        )
        return AnthropicProvider(
            api_key=api_key or s.anthropic_api_key,
            model=model or s.anthropic_model,
            fallback_embed_provider=embed_fallback,
        )
    if provider == "openrouter":
        return OpenRouterProvider(
            api_key=api_key or s.openrouter_api_key,
            base_url=base_url or s.openrouter_base_url,
            model=model or s.openrouter_model,
        )
    if provider == "gemini":
        return GeminiProvider(
            api_key=api_key or s.gemini_api_key,
            base_url=base_url or s.gemini_base_url,
            model=model or s.gemini_model,
            embed_model=embed_model or s.gemini_embed_model,
        )
    return FallbackProvider()


def _from_default(row: UserLLMSettings | None) -> LLMProvider:
    """Build a provider from the user's default profile (or env defaults)."""
    settings = get_settings()
    if row is not None:
        return build_provider(
            row.provider or settings.llm_provider,
            base_url=row.base_url,
            model=row.model,
            embed_model=row.embed_model,
            api_key=decrypt_secret(row.api_key_ciphertext),
        )
    return build_provider(settings.llm_provider, base_url="", model="", embed_model="", api_key="")


def _from_profile(prof: LLMProfile) -> LLMProvider:
    return build_provider(
        prof.provider,
        base_url=prof.base_url,
        model=prof.model,
        embed_model=prof.embed_model,
        api_key=decrypt_secret(prof.api_key_ciphertext),
    )


async def get_provider_for_user(db: AsyncSession, user: User) -> LLMProvider:
    """Back-compat: the user's default profile. Used by /status and anywhere
    that doesn't carry a page/category."""
    return _from_default(await get_user_settings(db, user))


async def get_provider_for_page(db: AsyncSession, user: User, page: str) -> LLMProvider:
    """Resolve the provider for a specific task `page`, honoring the user's mode.

      single → default profile (current behavior, zero change)
      split  → creative|technical profile by category, fall back to default
      custom → exact task:<page> profile, then category, then default
    """
    row = await get_user_settings(db, user)
    mode = (row.mode if row else "single") or "single"
    if mode == "single":
        return _from_default(row)

    category = category_for_page(page)  # creative | technical
    roles_to_try = [f"task:{page}", category] if mode == "custom" else [category]
    for role in roles_to_try:
        prof = await _get_profile(db, user, role)
        if prof is not None:
            return _from_profile(prof)
    return _from_default(row)


async def get_embedding_provider(db: AsyncSession, user: User) -> LLMProvider:
    """Resolve the embedding provider. Must be embed-capable — if the chosen
    config points at a non-embedding provider (Anthropic / OpenRouter), fall
    back to local LM Studio."""
    prof = await _get_profile(db, user, "embedding")
    if prof is not None and prof.provider in EMBED_CAPABLE:
        return _from_profile(prof)
    row = await get_user_settings(db, user)
    if row is not None and (row.provider or "") in EMBED_CAPABLE:
        return _from_default(row)
    # Safe local embedder regardless of other settings.
    return build_provider("lmstudio", base_url="", model="", embed_model="", api_key="")
