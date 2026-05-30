"""Google Gemini provider via its OpenAI-compatible endpoint.

Gemini exposes an OpenAI-compatible surface at
  https://generativelanguage.googleapis.com/v1beta/openai/
covering both chat/completions AND embeddings, so we reuse OpenAIProvider
wholesale. Gemini IS embed-capable (text-embedding-004), so the factory keeps
it in EMBED_CAPABLE.

Chat models: "gemini-2.0-flash", "gemini-1.5-pro", etc.
Embedding model: "text-embedding-004".
"""
from __future__ import annotations

from app.services.llm.openai_provider import OpenAIProvider

GEMINI_OPENAI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"


class GeminiProvider(OpenAIProvider):
    name = "gemini"

    def __init__(self, *, api_key: str, base_url: str, model: str, embed_model: str):
        super().__init__(
            api_key=api_key,
            base_url=base_url or GEMINI_OPENAI_BASE,
            model=model or "gemini-2.0-flash",
            embed_model=embed_model or "text-embedding-004",
        )
