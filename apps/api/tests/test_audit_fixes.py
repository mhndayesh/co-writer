"""Tests for the backend audit hardening pass:

- C1  context_builder budget packing (priority drop, always-keep sections)
- H6  opt-in pagination on studio list endpoints (backward compatible)
- H8  Idempotency-Key dedupe on Flow approve (no double-commit on retry)
"""
import pytest

from app.services.context_builder import (
    CONTEXT_CHAR_BUDGET,
    _ALWAYS_KEEP,
    _pack,
)


# ── C1: context budget packing (pure function) ──────────────────────────────

def test_pack_under_budget_keeps_everything_in_order():
    sections = [
        (100, ["# WORLD", "Title: X"]),
        (95, ["# CAST", "- A", "- B"]),
        (25, ["# VOICE", "- A: stats"]),
    ]
    out = _pack(sections, budget=CONTEXT_CHAR_BUDGET)
    # Every section present, original order preserved.
    assert out.index("# WORLD") < out.index("# CAST") < out.index("# VOICE")
    assert "- A: stats" in out


def test_pack_over_budget_drops_lowest_priority_first():
    big = ["# SCENES"] + [f"- scene {i} with some descriptive text" for i in range(200)]
    sections = [
        (100, ["# WORLD", "Title: X"]),
        (95, ["# CAST", "- A", "- B"]),
        (42, big),  # low priority, large
    ]
    out = _pack(sections, budget=400)
    # World + cast survive; the bulky low-priority scenes block is dropped.
    assert "# WORLD" in out
    assert "# CAST" in out
    assert "# SCENES" not in out


def test_pack_never_drops_always_keep_even_when_huge():
    huge_cast = ["# CAST"] + [f"- Character {i} — a long descriptive line here" for i in range(500)]
    sections = [
        (100, ["# WORLD", "Title: X"]),
        (_ALWAYS_KEEP + 1, huge_cast),  # above the always-keep threshold
    ]
    out = _pack(sections, budget=100)  # absurdly small budget
    # Cast is load-bearing for extract's is_new — must never be dropped.
    assert "# CAST" in out
    assert "Character 499" in out


# ── shared helpers ──────────────────────────────────────────────────────────

async def _signup(client, email):
    r = await client.post(
        "/v1/auth/signup",
        json={"email": email, "password": "password123", "display_name": "T"},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['tokens']['access_token']}"}


async def _make_story(client, H, title="Tale"):
    r = await client.post("/v1/stories", json={"title": title, "genre": "Fantasy"}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()["data"]["story"]["id"]


def _approve_payload():
    extract = {
        "title_suggestion": "Ch",
        "summary": "s",
        "pov_suggestion": "Mira",
        "location_suggestion": "Hall",
        "characters": [{"name": "Mira", "role": "protagonist", "note": "", "is_new": True}],
        "events": [],
        "relationships": [],
        "themes": [],
        "locations": [],
        "factions": [],
        "threads": [],
        "scenes": [],
    }
    return {
        "raw": "Mira spoke.",
        "polished": "Mira spoke.",
        "extracted": extract,
        "include_character_names": ["Mira"],
        "chapter_title": "Only Chapter",
        "chapter_summary": "x",
    }


# ── H6: pagination is opt-in and backward compatible ────────────────────────

@pytest.mark.asyncio
async def test_pagination_opt_in(client):
    H = await _signup(client, "paging@example.com")
    # three stories
    for i in range(3):
        await _make_story(client, H, title=f"S{i}")

    # No limit → all returned (current behavior preserved).
    r = await client.get("/v1/stories", headers=H)
    assert r.status_code == 200
    assert len(r.json()["data"]["stories"]) == 3

    # limit=1 → exactly one.
    r = await client.get("/v1/stories?limit=1", headers=H)
    assert r.status_code == 200
    assert len(r.json()["data"]["stories"]) == 1

    # offset paging walks the list.
    r = await client.get("/v1/stories?limit=2&offset=2", headers=H)
    assert len(r.json()["data"]["stories"]) == 1


# ── H8: idempotent approve ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_approve_idempotency_key_prevents_double_commit(client):
    H = await _signup(client, "idem@example.com")
    sid = await _make_story(client, H)
    payload = _approve_payload()

    headers = {**H, "Idempotency-Key": "approve-abc-123"}
    r1 = await client.post(f"/v1/stories/{sid}/flow/approve", json=payload, headers=headers)
    assert r1.status_code == 200, r1.text
    first = r1.json()["data"]

    # Same key again → same response, NO second chapter created.
    r2 = await client.post(f"/v1/stories/{sid}/flow/approve", json=payload, headers=headers)
    assert r2.status_code == 200, r2.text
    second = r2.json()["data"]
    assert second["chapter_id"] == first["chapter_id"]
    assert second["version_no"] == first["version_no"]

    r = await client.get(f"/v1/stories/{sid}/chapters", headers=H)
    assert len(r.json()["data"]["chapters"]) == 1  # exactly one, not two


@pytest.mark.asyncio
async def test_approve_without_key_is_not_deduped(client):
    H = await _signup(client, "nokey@example.com")
    sid = await _make_story(client, H)
    payload = _approve_payload()

    # No Idempotency-Key → each call commits (existing behavior unchanged).
    r1 = await client.post(f"/v1/stories/{sid}/flow/approve", json=payload, headers=H)
    r2 = await client.post(f"/v1/stories/{sid}/flow/approve", json=payload, headers=H)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["data"]["chapter_id"] != r2.json()["data"]["chapter_id"]
