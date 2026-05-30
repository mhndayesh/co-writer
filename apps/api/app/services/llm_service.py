"""The only entry point for LLM calls. Logs every run, catches errors, falls back.

Every AI feature in this codebase must go through `run()` — no router should
talk to a provider directly. This guarantees consistent logging, telemetry,
and graceful degradation when the configured provider is unreachable.
"""
from __future__ import annotations

import json
import logging
import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LLMRun, User
from app.services.llm.base import ChatResponse, LLMProvider, Message
from app.services.llm.factory import get_provider_for_page
from app.services.llm.fallback import FallbackProvider

log = logging.getLogger("gink.llm")


def _excerpt(text: str, n: int = 800) -> str:
    return text if len(text) <= n else text[:n] + "…"


async def run(
    db: AsyncSession,
    user: User,
    *,
    page: str,
    system: str,
    user_msg: str,
    json_mode: bool = False,
    temperature: float = 0.7,
    max_tokens: int | None = None,
    story_id: str | None = None,
    provider: LLMProvider | None = None,
) -> tuple[ChatResponse, bool]:
    """Run a chat completion; log result; return (response, used_fallback).

    If the real provider raises, retry once on the FallbackProvider so the
    caller always gets a response.
    """
    if provider is None:
        provider = await get_provider_for_page(db, user, page)

    messages = [Message("system", system), Message("user", user_msg)]
    started = time.monotonic()
    fallback_used = False
    error = ""

    try:
        resp = await provider.chat(
            messages,
            json_mode=json_mode,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception as e:
        log.warning("Provider %s failed (%s); using fallback", provider.name, e)
        fallback_used = True
        error = str(e)
        resp = await FallbackProvider().chat(messages, json_mode=json_mode)

    elapsed_ms = (time.monotonic() - started) * 1000.0

    run_row = LLMRun(
        user_id=user.id,
        story_id=story_id,
        provider=("fallback" if fallback_used else provider.name),
        model=resp.model,
        page=page,
        prompt_excerpt=_excerpt(f"SYSTEM:\n{system}\n\nUSER:\n{user_msg}"),
        response_excerpt=_excerpt(resp.text),
        tokens_in=resp.tokens_in,
        tokens_out=resp.tokens_out,
        ms=elapsed_ms,
        fallback=fallback_used,
        error=error,
    )
    db.add(run_row)
    await db.flush()

    return resp, fallback_used


def parse_json(text: str) -> dict | list | None:
    """Best-effort JSON parse: strips code fences, recovers from truncation.

    Reasoning models often run out of tokens mid-object; we close any unclosed
    brackets and trim trailing commas so the partial response still parses.
    """
    if not text:
        return None
    t = text.strip()
    # Strip <think>...</think> blocks first
    import re as _re
    t = _re.sub(r"<think>.*?</think>", "", t, flags=_re.DOTALL | _re.IGNORECASE).strip()
    # Strip a markdown fence if present
    if t.startswith("```"):
        t = t.strip("`")
        if t.startswith("json"):
            t = t[4:]
        t = t.strip()

    # Direct parse
    try:
        return json.loads(t)
    except Exception:
        pass

    # Trim to the first balanced JSON object/array
    start = min((i for i in (t.find("{"), t.find("[")) if i >= 0), default=-1)
    if start < 0:
        return None
    t = t[start:]

    try:
        return json.loads(t)
    except Exception:
        pass

    # Attempt to repair truncated JSON by closing open brackets/quotes
    repaired = _repair_truncated_json(t)
    if repaired:
        try:
            return json.loads(repaired)
        except Exception:
            pass
    return None


def _repair_truncated_json(t: str) -> str | None:
    """Close unclosed strings, arrays, and objects so a truncated response parses.

    Walks the string respecting string quoting + escapes; at the end, appends
    whatever closers are needed in the right order.
    """
    stack: list[str] = []
    in_string = False
    escape = False
    last_complete = 0  # position of last char that left us at a clean state

    for i, ch in enumerate(t):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if stack and stack[-1] == ch:
                stack.pop()
            else:
                return None  # mismatched — can't safely repair
        if not in_string and not stack:
            last_complete = i + 1

    # Trim trailing partial garbage after the last clean comma/colon
    s = t
    if in_string:
        # Close the open string
        s = s + '"'
    # Drop trailing comma-or-colon-and-junk before closing
    s = s.rstrip().rstrip(",").rstrip(":").rstrip()
    if s.endswith('"'):  # close key without value → drop it
        # Find the comma that precedes this dangling key/value pair
        depth = 0
        cut = -1
        in_s = False
        esc = False
        for i, ch in enumerate(s):
            if in_s:
                if esc: esc = False
                elif ch == "\\": esc = True
                elif ch == '"': in_s = False
                continue
            if ch == '"': in_s = True
            elif ch in "{[": depth += 1
            elif ch in "}]": depth -= 1
            elif ch == "," and depth == len(stack):
                cut = i
        if cut > 0:
            s = s[:cut]
    # Append closers in reverse stack order
    return s + "".join(reversed(stack))
