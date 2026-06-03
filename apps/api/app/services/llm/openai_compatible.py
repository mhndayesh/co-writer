"""One transport for every OpenAI-compatible provider (LM Studio, OpenAI,
OpenRouter, Gemini). Behavior differences are driven by the Preset, not by
subclasses — so adding a provider is a presets.py entry, not a new file.

Folds in the hard-won LM Studio quirks as flags so nothing is lost:
  • supports_response_format=False → inject a JSON system hint (local backends 400 on response_format)
  • no_max_tokens_sentinel=True    → send max_tokens:-1 when unbounded
  • always strip <think>…</think> and fall back to reasoning_content (harmless elsewhere)
"""
from __future__ import annotations

import json
import re
from typing import AsyncIterator

import httpx

from app.services.llm.base import ChatResponse, LLMProvider, Message
from app.services.llm.presets import Preset

# Strip <think>...</think> blocks emitted by reasoning models (Qwen3, DeepSeek-R1).
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

# OpenAI reasoning families (o1 / o3 / o4-…). They reject a non-default
# `temperature` (HTTP 400) and require `max_completion_tokens` instead of
# `max_tokens`. Match on the final path segment so "openai/o1-mini" works too.
_REASONING_RE = re.compile(r"^o\d", re.IGNORECASE)


def _is_reasoning_model(model: str) -> bool:
    return bool(_REASONING_RE.match((model or "").split("/")[-1].strip()))


# Placeholder model names that mean "whatever LM Studio currently has loaded".
# When configured with one of these, we resolve the real id from /models at call
# time — so swapping the loaded model in LM Studio never causes a 400, and a
# multi-model LM Studio (which REQUIRES an explicit, valid `model`) just works.
_PLACEHOLDER_MODELS = {"", "local-model", "default", "auto"}


# Explicit timeouts so a hung/slow upstream eventually raises and falls back
# (the old `timeout=None` let a stalled backend pin the request forever, which
# silently defeated llm_service.run's fallback-on-exception path).
_CHAT_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)


def clean_response(text: str) -> str:
    text = _THINK_RE.sub("", text or "")
    if "<think>" in text.lower():
        idx = text.lower().rfind("</think>")
        if idx >= 0:
            text = text[idx + len("</think>"):]
        else:
            text = text.split("<think>", 1)[0]
    return text.strip()


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, preset: Preset, *, base_url: str, model: str, embed_model: str, api_key: str,
                 revalidate_base_url: bool = False):
        self.preset = preset
        self.name = preset.name  # so llm_runs.provider stays meaningful
        self.api_key = api_key
        self.base_url = (base_url or preset.base_url).rstrip("/")
        self.default_model = model or preset.default_model
        self.default_embed_model = embed_model or preset.default_embed_model
        self._resolved_model: str | None = None  # cache for placeholder resolution
        # True when base_url came from a USER (BYOK lane / owner house default) and
        # must be re-checked for SSRF before each outbound call (DNS-rebind guard).
        # Preset/localhost base_urls are trusted and never re-validated.
        self._revalidate_base_url = revalidate_base_url

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json", **self.preset.extra_headers}
        if self.preset.auth == "bearer":
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _guard_url(self) -> None:
        """SSRF re-check before any outbound request to a user-supplied base_url."""
        if self._revalidate_base_url:
            from app.core.ssrf import assert_base_url_safe
            assert_base_url_safe(self.base_url)

    async def _resolve_model(self, requested: str | None) -> str:
        """Pick the model id to send. An explicit per-call `requested` wins. Else if
        the configured default is a placeholder ('local-model' etc.), query /models
        and use the first loaded one (cached) — so a model swap in LM Studio, or a
        multi-model server that demands an explicit id, never 400s us."""
        if requested:
            return requested
        configured = (self.default_model or "").strip()
        if configured.lower() not in _PLACEHOLDER_MODELS:
            return configured
        if self._resolved_model:
            return self._resolved_model
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(f"{self.base_url}/models", headers=self._headers())
                r.raise_for_status()
                items = (r.json() or {}).get("data") or []
            # Prefer a non-embedding chat model; fall back to the first listed.
            ids = [m.get("id", "") for m in items if m.get("id")]
            chat_ids = [i for i in ids if "embed" not in i.lower()]
            picked = (chat_ids or ids or [configured])[0]
            self._resolved_model = picked
            return picked
        except Exception:
            # /models unreachable — return the configured value and let the call
            # surface its own error (which falls back deterministically upstream).
            return configured

    async def chat(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        json_mode: bool = False,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        self._guard_url()  # SSRF re-check before any network call to a user URL
        msgs = [{"role": m.role, "content": m.content} for m in messages]

        if json_mode and not self.preset.supports_response_format:
            # Inject a JSON hint into the system message rather than using response_format.
            hint = "Reply with a single valid JSON object only. No prose, no markdown, no code fences."
            if msgs and msgs[0]["role"] == "system":
                msgs[0]["content"] = hint + "\n\n" + msgs[0]["content"]
            else:
                msgs.insert(0, {"role": "system", "content": hint})

        effective_model = await self._resolve_model(model)
        is_reasoning = _is_reasoning_model(effective_model)

        body: dict = {"model": effective_model, "messages": msgs}
        # Reasoning models (o1/o3/…) 400 on any non-default temperature — omit it.
        if not is_reasoning:
            body["temperature"] = temperature
        if json_mode and self.preset.supports_response_format:
            body["response_format"] = {"type": "json_object"}
        if max_tokens is not None and max_tokens > 0:
            # Reasoning models reject `max_tokens`; they use `max_completion_tokens`.
            body["max_completion_tokens" if is_reasoning else "max_tokens"] = max_tokens
        elif self.preset.no_max_tokens_sentinel and not is_reasoning:
            body["max_tokens"] = -1  # LM Studio: use the model's full context

        async with httpx.AsyncClient(timeout=_CHAT_TIMEOUT) as client:
            r = await client.post(f"{self.base_url}/chat/completions", json=body, headers=self._headers())
            r.raise_for_status()
            data = r.json()

        msg = data["choices"][0]["message"]
        text = clean_response(msg.get("content") or msg.get("reasoning_content") or "")
        usage = data.get("usage", {}) or {}
        return ChatResponse(
            text=text,
            model=data.get("model", body["model"]),
            tokens_in=usage.get("prompt_tokens", 0),
            tokens_out=usage.get("completion_tokens", 0),
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
        self._guard_url()  # SSRF re-check before any network call to a user URL
        msgs = [{"role": m.role, "content": m.content} for m in messages]
        effective_model = await self._resolve_model(model)
        is_reasoning = _is_reasoning_model(effective_model)

        body: dict = {"model": effective_model, "messages": msgs, "stream": True}
        if not is_reasoning:
            body["temperature"] = temperature
        if max_tokens is not None and max_tokens > 0:
            body["max_completion_tokens" if is_reasoning else "max_tokens"] = max_tokens
        elif self.preset.no_max_tokens_sentinel and not is_reasoning:
            body["max_tokens"] = -1

        async with httpx.AsyncClient(timeout=_CHAT_TIMEOUT) as client:
            async with client.stream(
                "POST", f"{self.base_url}/chat/completions", json=body, headers=self._headers()
            ) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                        delta = (obj["choices"][0].get("delta") or {}).get("content") or ""
                    except Exception:
                        continue
                    if delta:
                        yield delta

    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        if not self.preset.can_embed:
            raise RuntimeError(f"{self.name} has no embeddings API")
        self._guard_url()  # SSRF re-check before any network call to a user URL
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                f"{self.base_url}/embeddings",
                json={"model": model or self.default_embed_model, "input": texts},
                headers=self._headers(),
            )
            r.raise_for_status()
            data = r.json()
        return [item["embedding"] for item in data["data"]]

    async def ping(self) -> tuple[bool, str]:
        if self.preset.auth == "bearer" and not self.api_key:
            return False, "missing API key"
        try:
            self._guard_url()  # SSRF re-check before any network call to a user URL
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(f"{self.base_url}/models", headers=self._headers())
                return (True, "ok") if r.status_code == 200 else (False, f"HTTP {r.status_code}")
        except Exception as e:
            return False, str(e)

    async def list_models(self) -> list[dict]:
        """List models from the provider's OpenAI-compatible `/models` endpoint.
        Works for LM Studio (local, no key), OpenAI, OpenRouter and Gemini (the
        last three need the bearer key). Returns chat models first, then embed."""
        if self.preset.auth == "bearer" and not self.api_key:
            raise RuntimeError("missing API key")
        self._guard_url()  # SSRF re-check before any network call to a user URL
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{self.base_url}/models", headers=self._headers())
            r.raise_for_status()
            data = r.json() or {}
        items = data.get("data") or data.get("models") or []
        out: list[dict] = []
        seen: set[str] = set()
        for it in items:
            if isinstance(it, str):
                mid, label = it, it
            elif isinstance(it, dict):
                mid = it.get("id") or it.get("name") or ""
                label = it.get("name") or it.get("id") or mid
            else:
                continue
            # Gemini's OpenAI-compat list prefixes ids with "models/"; the chat
            # call wants the bare name, so strip it for both id and label.
            if self.name == "gemini" and isinstance(mid, str) and mid.startswith("models/"):
                mid = mid[len("models/"):]
                if isinstance(label, str) and label.startswith("models/"):
                    label = label[len("models/"):]
            if not mid or mid in seen:
                continue
            seen.add(mid)
            kind = "embed" if "embed" in mid.lower() else "chat"
            out.append({"id": mid, "label": label or mid, "kind": kind})
        out.sort(key=lambda m: (m["kind"] != "chat", m["id"].lower()))
        return out
