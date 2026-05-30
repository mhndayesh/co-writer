from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

Role = Literal["system", "user", "assistant"]


@dataclass
class Message:
    role: Role
    content: str


@dataclass
class ChatResponse:
    text: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    raw: dict = field(default_factory=dict)


class LLMProvider(Protocol):
    name: str
    default_model: str
    default_embed_model: str

    async def chat(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        json_mode: bool = False,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> ChatResponse: ...

    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]: ...

    async def ping(self) -> tuple[bool, str]: ...
