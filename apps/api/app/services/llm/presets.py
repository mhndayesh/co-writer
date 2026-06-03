"""Provider presets — the single source of truth for each supported provider.

Adding a new OpenAI-compatible provider (Groq, Together, Mistral, …) is one
new entry here: no new class, no branching in the router. Only genuinely
different transports (currently just Anthropic's native Messages API) need a
dedicated provider class.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Preset:
    name: str
    transport: str  # "openai" | "anthropic"
    base_url: str = ""
    default_model: str = ""
    default_embed_model: str = ""
    auth: str = "bearer"  # "bearer" | "x-api-key" | "none"
    can_embed: bool = True
    # OpenAI-compatible quirks (ignored by the anthropic transport):
    supports_response_format: bool = True  # False → inject a JSON system hint instead
    no_max_tokens_sentinel: bool = False   # True → send max_tokens:-1 when unbounded (LM Studio)
    extra_headers: dict[str, str] = field(default_factory=dict)


PRESETS: dict[str, Preset] = {
    "lmstudio": Preset(
        name="lmstudio",
        transport="openai",
        base_url="http://localhost:1234/v1",
        default_model="local-model",
        default_embed_model="nomic-embed-text-v1.5",
        auth="none",
        can_embed=True,
        supports_response_format=False,  # many local backends 400 on response_format
        no_max_tokens_sentinel=False,    # omit max_tokens entirely → LM Studio uses its own default
    ),
    "openai": Preset(
        name="openai",
        transport="openai",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
        default_embed_model="text-embedding-3-small",
        auth="bearer",
        can_embed=True,
    ),
    "openrouter": Preset(
        name="openrouter",
        transport="openai",
        base_url="https://openrouter.ai/api/v1",
        default_model="openai/gpt-4o-mini",
        auth="bearer",
        can_embed=False,  # OpenRouter is a chat router; no embeddings endpoint
        extra_headers={
            "HTTP-Referer": "https://github.com/mhndayesh/co-writer",
            "X-Title": "G-Ink Novel Studio",
        },
    ),
    "gemini": Preset(
        name="gemini",
        transport="openai",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        default_model="gemini-2.0-flash",
        default_embed_model="text-embedding-004",
        auth="bearer",
        can_embed=True,
    ),
    "deepseek": Preset(
        name="deepseek",
        transport="openai",  # OpenAI-compatible API
        base_url="https://api.deepseek.com/v1",
        default_model="deepseek-v4-flash",
        auth="bearer",
        can_embed=False,  # no embeddings API → embedding lane falls back to local LM Studio
        supports_response_format=True,  # JSON mode (response_format) is supported
    ),
    "anthropic": Preset(
        name="anthropic",
        transport="anthropic",
        default_model="claude-sonnet-4-5",
        auth="x-api-key",
        can_embed=False,  # no embeddings API → router falls back to local LM Studio
    ),
}

PROVIDER_NAMES = tuple(PRESETS.keys())
EMBED_CAPABLE = tuple(name for name, p in PRESETS.items() if p.can_embed)


def get_preset(name: str) -> Preset | None:
    return PRESETS.get(name)
