"""OpenRouter provider — OpenAI-compatible chat gateway to many models.

OpenRouter (https://openrouter.ai/api/v1) speaks the OpenAI chat protocol, so
we reuse OpenAIProvider's chat/ping. It does NOT serve embeddings (it's a chat
router), so embed() raises and the factory keeps it out of EMBED_CAPABLE —
embedding work falls back to a local embedder.

Model names are namespaced, e.g. "anthropic/claude-sonnet-4.5",
"google/gemini-2.0-flash-exp", "meta-llama/llama-3.3-70b-instruct".
"""
from __future__ import annotations

from app.services.llm.openai_provider import OpenAIProvider


class OpenRouterProvider(OpenAIProvider):
    name = "openrouter"

    def __init__(self, *, api_key: str, base_url: str, model: str, embed_model: str = ""):
        super().__init__(
            api_key=api_key,
            base_url=base_url or "https://openrouter.ai/api/v1",
            model=model or "openai/gpt-4o-mini",
            embed_model=embed_model,  # unused; OpenRouter has no embeddings
        )

    def _headers(self) -> dict:
        # OpenRouter recommends (optional) attribution headers.
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/g-ink-novel-studio",
            "X-Title": "G-Ink Novel Studio",
        }

    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        raise RuntimeError("OpenRouter does not provide embeddings; use a local or OpenAI/Gemini embedder")
