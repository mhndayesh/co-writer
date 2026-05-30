"""One transport for every OpenAI-compatible provider (LM Studio, OpenAI,
OpenRouter, Gemini). Behavior differences are driven by the Preset, not by
subclasses — so adding a provider is a presets.py entry, not a new file.

Folds in the hard-won LM Studio quirks as flags so nothing is lost:
  • supports_response_format=False → inject a JSON system hint (local backends 400 on response_format)
  • no_max_tokens_sentinel=True    → send max_tokens:-1 when unbounded
  • always strip <think>…</think> and fall back to reasoning_content (harmless elsewhere)
"""
from __future__ import annotations

import re

import httpx

from app.services.llm.base import ChatResponse, LLMProvider, Message
from app.services.llm.presets import Preset

# Strip <think>...</think> blocks emitted by reasoning models (Qwen3, DeepSeek-R1).
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


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
    def __init__(self, preset: Preset, *, base_url: str, model: str, embed_model: str, api_key: str):
        self.preset = preset
        self.name = preset.name  # so llm_runs.provider stays meaningful
        self.api_key = api_key
        self.base_url = (base_url or preset.base_url).rstrip("/")
        self.default_model = model or preset.default_model
        self.default_embed_model = embed_model or preset.default_embed_model

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json", **self.preset.extra_headers}
        if self.preset.auth == "bearer":
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    async def chat(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        json_mode: bool = False,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        msgs = [{"role": m.role, "content": m.content} for m in messages]

        if json_mode and not self.preset.supports_response_format:
            # Inject a JSON hint into the system message rather than using response_format.
            hint = "Reply with a single valid JSON object only. No prose, no markdown, no code fences."
            if msgs and msgs[0]["role"] == "system":
                msgs[0]["content"] = hint + "\n\n" + msgs[0]["content"]
            else:
                msgs.insert(0, {"role": "system", "content": hint})

        body: dict = {"model": model or self.default_model, "messages": msgs, "temperature": temperature}
        if json_mode and self.preset.supports_response_format:
            body["response_format"] = {"type": "json_object"}
        if max_tokens is not None and max_tokens > 0:
            body["max_tokens"] = max_tokens
        elif self.preset.no_max_tokens_sentinel:
            body["max_tokens"] = -1  # LM Studio: use the model's full context

        async with httpx.AsyncClient(timeout=None) as client:
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

    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        if not self.preset.can_embed:
            raise RuntimeError(f"{self.name} has no embeddings API")
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
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(f"{self.base_url}/models", headers=self._headers())
                return (True, "ok") if r.status_code == 200 else (False, f"HTTP {r.status_code}")
        except Exception as e:
            return False, str(e)
