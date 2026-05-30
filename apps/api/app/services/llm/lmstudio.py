"""LM Studio provider — OpenAI-compatible HTTP endpoint at localhost:1234/v1 by default."""
from __future__ import annotations

import re

import httpx

from app.services.llm.base import ChatResponse, LLMProvider, Message

# Strip <think>...</think> blocks emitted by reasoning models (Qwen3, DeepSeek-R1, etc.)
# so the model's internal reasoning doesn't leak into prose output.
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _clean_response(text: str) -> str:
    text = _THINK_RE.sub("", text or "")
    # If the model started thinking but never closed (hit max_tokens mid-reasoning),
    # drop everything before the last </think>; if no closer, drop the open tag's tail.
    if "<think>" in text.lower():
        idx = text.lower().rfind("</think>")
        if idx >= 0:
            text = text[idx + len("</think>"):]
        else:
            text = text.split("<think>", 1)[0]
    return text.strip()


class LMStudioProvider(LLMProvider):
    name = "lmstudio"

    def __init__(self, *, base_url: str, model: str, embed_model: str):
        self.base_url = base_url.rstrip("/")
        self.default_model = model or "local-model"
        self.default_embed_model = embed_model or "nomic-embed-text-v1.5"

    async def chat(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        json_mode: bool = False,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        # Don't send response_format — many LM Studio backends (esp. with reasoning
        # models like Qwen3) return HTTP 400. Instead, hint JSON via a system prefix.
        msgs = [{"role": m.role, "content": m.content} for m in messages]
        if json_mode:
            json_hint = "Reply with a single valid JSON object only. No prose, no markdown, no code fences."
            if msgs and msgs[0]["role"] == "system":
                msgs[0]["content"] = json_hint + "\n\n" + msgs[0]["content"]
            else:
                msgs.insert(0, {"role": "system", "content": json_hint})
        body: dict = {
            "model": model or self.default_model,
            "messages": msgs,
            "temperature": temperature,
        }
        # Omit max_tokens to let LM Studio use the model's full remaining context.
        # Pass -1 explicitly for backends that need it.
        if max_tokens is not None and max_tokens > 0:
            body["max_tokens"] = max_tokens
        else:
            body["max_tokens"] = -1
        async with httpx.AsyncClient(timeout=180) as client:
            r = await client.post(f"{self.base_url}/chat/completions", json=body)
            r.raise_for_status()
            data = r.json()
        msg = data["choices"][0]["message"]
        # Some local servers return reasoning in `reasoning_content` and leave `content` empty;
        # others embed <think>...</think> inside `content`. Prefer content, fall back to reasoning.
        text = msg.get("content") or msg.get("reasoning_content") or ""
        text = _clean_response(text)
        usage = data.get("usage", {}) or {}
        return ChatResponse(
            text=text,
            model=data.get("model", body["model"]),
            tokens_in=usage.get("prompt_tokens", 0),
            tokens_out=usage.get("completion_tokens", 0),
            raw=data,
        )

    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                f"{self.base_url}/embeddings",
                json={"model": model or self.default_embed_model, "input": texts},
            )
            r.raise_for_status()
            data = r.json()
        return [item["embedding"] for item in data["data"]]

    async def ping(self) -> tuple[bool, str]:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{self.base_url}/models")
                if r.status_code == 200:
                    return True, "ok"
                return False, f"HTTP {r.status_code}"
        except Exception as e:
            return False, str(e)
