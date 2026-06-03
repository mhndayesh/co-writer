from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from app.services.llm.base import ChatResponse, LLMProvider, Message


class AnthropicProvider(LLMProvider):
    """Anthropic Messages API. Embeddings: delegates to a sibling provider since Anthropic has no embeddings."""

    name = "anthropic"

    def __init__(self, *, api_key: str, model: str, fallback_embed_provider: LLMProvider | None = None):
        self.api_key = api_key
        self.default_model = model or "claude-sonnet-4-5"
        self.default_embed_model = ""
        self._fallback_embed_provider = fallback_embed_provider

    def _headers(self) -> dict:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

    async def chat(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        json_mode: bool = False,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        system_chunks = [m.content for m in messages if m.role == "system"]
        non_system = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]

        # Hint JSON via system addendum since Anthropic doesn't take response_format.
        sys_text = "\n\n".join(system_chunks).strip()
        if json_mode:
            sys_text = (sys_text + "\n\nReturn a single JSON object only. No prose, no code fences.").strip()

        body = {
            "model": model or self.default_model,
            "messages": non_system,
            # Anthropic REQUIRES max_tokens. Default to a generous 16k if unset.
            "max_tokens": max_tokens if (max_tokens and max_tokens > 0) else 16000,
            "temperature": temperature,
        }
        if sys_text:
            body["system"] = sys_text

        async with httpx.AsyncClient(timeout=180) as client:
            r = await client.post("https://api.anthropic.com/v1/messages", json=body, headers=self._headers())
            r.raise_for_status()
            data = r.json()

        parts = data.get("content") or []
        text = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
        usage = data.get("usage", {}) or {}
        return ChatResponse(
            text=text,
            model=data.get("model", body["model"]),
            tokens_in=usage.get("input_tokens", 0),
            tokens_out=usage.get("output_tokens", 0),
            raw=data,
        )

    async def stream(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        system_chunks = [m.content for m in messages if m.role == "system"]
        non_system = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
        body = {
            "model": model or self.default_model,
            "messages": non_system,
            "max_tokens": max_tokens if (max_tokens and max_tokens > 0) else 16000,
            "temperature": temperature,
            "stream": True,
        }
        sys_text = "\n\n".join(system_chunks).strip()
        if sys_text:
            body["system"] = sys_text

        async with httpx.AsyncClient(timeout=180) as client:
            async with client.stream(
                "POST", "https://api.anthropic.com/v1/messages", json=body, headers=self._headers()
            ) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if not data:
                        continue
                    try:
                        obj = json.loads(data)
                    except Exception:
                        continue
                    if obj.get("type") == "content_block_delta":
                        piece = (obj.get("delta") or {}).get("text") or ""
                        if piece:
                            yield piece

    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        if self._fallback_embed_provider is None:
            raise RuntimeError("Anthropic has no embeddings API; configure a sibling embed provider")
        return await self._fallback_embed_provider.embed(texts, model=model)

    async def list_models(self) -> list[dict]:
        """List models from Anthropic's native /v1/models (needs x-api-key +
        anthropic-version). Anthropic has no embeddings, so all are chat."""
        if not self.api_key:
            raise RuntimeError("missing API key")
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                "https://api.anthropic.com/v1/models?limit=100", headers=self._headers()
            )
            r.raise_for_status()
            data = r.json() or {}
        out: list[dict] = []
        for it in (data.get("data") or []):
            mid = it.get("id")
            if not mid:
                continue
            out.append({"id": mid, "label": it.get("display_name") or mid, "kind": "chat"})
        return out

    async def ping(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "missing API key"
        # Cheap ping: a one-token completion.
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    json={
                        "model": self.default_model,
                        "messages": [{"role": "user", "content": "hi"}],
                        "max_tokens": 1,
                    },
                    headers=self._headers(),
                )
                if r.status_code in (200, 201):
                    return True, "ok"
                return False, f"HTTP {r.status_code}: {r.text[:120]}"
        except Exception as e:
            return False, str(e)
