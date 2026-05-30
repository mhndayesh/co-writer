from __future__ import annotations

import httpx

from app.services.llm.base import ChatResponse, LLMProvider, Message
from app.services.llm.lmstudio import _clean_response


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, *, api_key: str, base_url: str, model: str, embed_model: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.default_model = model or "gpt-4o-mini"
        self.default_embed_model = embed_model or "text-embedding-3-small"

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def chat(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        json_mode: bool = False,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        body: dict = {
            "model": model or self.default_model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
        }
        if max_tokens is not None and max_tokens > 0:
            body["max_tokens"] = max_tokens
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        async with httpx.AsyncClient(timeout=180) as client:
            r = await client.post(f"{self.base_url}/chat/completions", json=body, headers=self._headers())
            r.raise_for_status()
            data = r.json()
        msg = data["choices"][0]["message"]
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
                headers=self._headers(),
            )
            r.raise_for_status()
            data = r.json()
        return [item["embedding"] for item in data["data"]]

    async def ping(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "missing API key"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(f"{self.base_url}/models", headers=self._headers())
                if r.status_code == 200:
                    return True, "ok"
                return False, f"HTTP {r.status_code}"
        except Exception as e:
            return False, str(e)
