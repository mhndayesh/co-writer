"""Deterministic fallback provider — used when no real LLM is reachable.

Returns plausible-looking text/JSON so the UI never breaks while the user
is still wiring up LM Studio / pasting an API key.
"""
from __future__ import annotations

import json
import re
import textwrap
from typing import AsyncIterator

from app.services.llm.base import ChatResponse, LLMProvider, Message


def _is_json_request(messages: list[Message]) -> bool:
    return any("json" in m.content.lower() for m in messages if m.role == "system")


def _first_user(messages: list[Message]) -> str:
    for m in reversed(messages):
        if m.role == "user":
            return m.content
    return ""


def _looks_like_polish(messages: list[Message]) -> bool:
    sys = "\n".join(m.content for m in messages if m.role == "system").lower()
    return "polish" in sys or "rewrite" in sys or "prose" in sys


def _looks_like_extract(messages: list[Message]) -> bool:
    sys = "\n".join(m.content for m in messages if m.role == "system").lower()
    return "extract" in sys and ("character" in sys or "event" in sys)


def _looks_like_check(messages: list[Message]) -> bool:
    sys = "\n".join(m.content for m in messages if m.role == "system").lower()
    return "continuity" in sys or "consistency" in sys or "story check" in sys


def _naive_chars(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"\b[A-Z][a-zA-Z]{2,}\b", text)))[:6]


class FallbackProvider(LLMProvider):
    name = "fallback"
    default_model = "fallback-stub"
    default_embed_model = "fallback-embed"

    async def chat(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        json_mode: bool = False,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        user = _first_user(messages)

        if json_mode or _is_json_request(messages):
            if _looks_like_extract(messages):
                # Don't guess. Returning fake characters scraped from the prompt's
                # own headers (STORY CONTEXT, WORLD, …) creates worse-than-useless
                # garbage. Empty arrays make it obvious that nothing was extracted.
                payload = {
                    "title_suggestion": "",
                    "summary": "",
                    "pov_suggestion": "",
                    "location_suggestion": "",
                    "characters": [],
                    "events": [],
                    "relationships": [],
                    "themes": [],
                    "locations": [],
                    "factions": [],
                    "threads": [],
                    "scenes": [],
                }
                return ChatResponse(text=json.dumps(payload), model="fallback-stub")
            if _looks_like_check(messages):
                payload = {
                    "findings": [
                        {
                            "severity": "low",
                            "title": "Continuity check unavailable",
                            "detail": "No LLM is configured. Connect LM Studio in Settings to run real continuity checks.",
                            "suggestion": "Open Settings → LLM Provider → Test connection.",
                        }
                    ],
                    "strengths": ["The scene reads cleanly."],
                    "severity_buckets": {"high": 0, "medium": 0, "low": 1},
                }
                return ChatResponse(text=json.dumps(payload), model="fallback-stub")
            return ChatResponse(text="{}", model="fallback-stub")

        if _looks_like_polish(messages):
            # Light formatting: trim, sentence-case opening, join fragments.
            t = re.sub(r"\s+", " ", user.strip())
            if t and t[0].islower():
                t = t[0].upper() + t[1:]
            polished = textwrap.fill(t, width=80) if t else "(empty draft)"
            return ChatResponse(text=polished, model="fallback-stub")

        return ChatResponse(
            text="(LLM unavailable — connect LM Studio in Settings to see real output.)",
            model="fallback-stub",
        )

    async def stream(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        # Deterministic: produce the full fallback text, then emit it in small
        # slices so a streaming client still sees incremental output.
        resp = await self.chat(messages, temperature=temperature, max_tokens=max_tokens)
        text = resp.text
        for i in range(0, len(text), 40):
            yield text[i:i + 40]

    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        # Deterministic 16-dim hash embedding so Qdrant write succeeds.
        out: list[list[float]] = []
        for t in texts:
            vec = [0.0] * 16
            for i, ch in enumerate(t.encode("utf-8")):
                vec[i % 16] += (ch / 255.0)
            n = (sum(v * v for v in vec) ** 0.5) or 1.0
            out.append([v / n for v in vec])
        return out

    async def ping(self) -> tuple[bool, str]:
        return True, "fallback"

    async def list_models(self) -> list[dict]:
        return []
