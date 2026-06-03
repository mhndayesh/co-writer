"""End-to-end smoke: signup → create story → flow polish → flow extract → approve
→ chapter exists → graph view returns nodes. Exercises the fallback LLM
provider (no LM Studio needed for CI).
"""
import pytest


@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


@pytest.mark.asyncio
async def test_full_flow(client):
    # 1. Sign up
    r = await client.post("/v1/auth/signup", json={"email": "alice@example.com", "password": "password123", "display_name": "Alice"})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    token = data["tokens"]["access_token"]
    H = {"Authorization": f"Bearer {token}"}

    # 2. Me
    r = await client.get("/v1/auth/me", headers=H)
    assert r.status_code == 200
    assert r.json()["data"]["user"]["email"] == "alice@example.com"

    # 3. Create story
    r = await client.post("/v1/stories", json={"title": "Smoke Tale", "genre": "Fantasy"}, headers=H)
    story = r.json()["data"]["story"]
    sid = story["id"]
    assert story["title"] == "Smoke Tale"

    # 4. PATCH world with rules + themes
    r = await client.patch(f"/v1/stories/{sid}/world", json={
        "rules": ["Magic costs a year of life per casting"],
        "themes": ["sacrifice"],
        "logline": "A witch trades her last decade for the world's last hope.",
    }, headers=H)
    assert r.status_code == 200
    world = r.json()["data"]["world"]
    assert "sacrifice" in world["themes"]

    # 5. LLM status (fallback because lmstudio unreachable in test env)
    r = await client.get("/v1/llm/status", headers=H)
    assert r.status_code == 200
    # provider may say lmstudio but reachable=False — that's fine

    raw_draft = 'Mira asked, "What did you do?" Aiden said, "I broke the pact under the moonlit arch."'

    # 6. Flow polish (uses fallback provider, returns plausible polished text)
    r = await client.post(f"/v1/stories/{sid}/flow/polish", json={"raw": raw_draft}, headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["polished"]
    polished = raw_draft

    # 7. Flow extract
    r = await client.post(f"/v1/stories/{sid}/flow/extract", json={"polished": polished}, headers=H)
    assert r.status_code == 200, r.text
    extract = r.json()["data"]
    assert "characters" in extract
    extract.update({
        "title_suggestion": "The Broken Pact",
        "summary": "Mira confronts Aiden after learning the pact has been broken.",
        "pov_suggestion": "Mira",
        "location_suggestion": "Throne Room",
        "characters": [
            {"name": "Mira", "role": "protagonist", "note": "demands the truth", "is_new": True},
            {"name": "Aiden", "role": "ally", "note": "admits he broke the pact", "is_new": True},
        ],
        "locations": [{"name": "Throne Room", "description": "A moonlit hall where the pact is exposed."}],
        "threads": [{"name": "Broken pact", "description": "The old oath has failed.", "status": "open"}],
        "scenes": [{
            "ordinal": 1,
            "title": "Mira Confronts Aiden",
            "beat": "revelation",
            "summary": "Aiden admits the pact is broken.",
            "goal": "Mira wants Aiden to tell the truth.",
            "conflict": "Aiden tries to soften the damage.",
            "outcome": "The reader and Mira know the pact has failed.",
            "pov": "Mira",
            "location": "Throne Room",
            "characters": ["Mira", "Aiden"],
            "plot_threads": ["Broken pact"],
            "time_anchor": "night of the coronation",
            "time_sort_key": 12.5,
            "duration_hint": "minutes",
            "sensory_palette": {"sight": 4, "sound": 3, "smell": 1, "taste": 0, "touch": 2},
            "revelations": [{
                "description": "Aiden broke the pact under the moonlit arch.",
                "kind": "secret",
                "characters_who_know": ["Mira", "Aiden"],
                "reader_knows": True,
                "notes": "This should feed the information ledger.",
                "confidence": 0.95,
            }],
            "source_excerpt": "Aiden said, \"I broke the pact under the moonlit arch.\"",
            "content": "Information economy beat.",
        }],
    })

    # 8. Approve — commit as new chapter, opt-in to any detected characters
    include = [c["name"] for c in extract["characters"] if c.get("is_new")]
    r = await client.post(f"/v1/stories/{sid}/flow/approve", json={
        "raw": raw_draft,
        "polished": polished,
        "extracted": extract,
        "include_character_names": include,
        "chapter_title": "The Reunion",
        "chapter_summary": "A tense throne-room meeting.",
    }, headers=H)
    assert r.status_code == 200, r.text
    approve = r.json()["data"]
    assert approve["version_no"] >= 1
    assert approve["scene_ids"]
    assert approve["revelation_ids"]
    assert approve["thread_scene_link_ids"]
    scene_id = approve["scene_ids"][0]

    # 9. Chapter list shows the new chapter
    r = await client.get(f"/v1/stories/{sid}/chapters", headers=H)
    assert r.status_code == 200
    chapters = r.json()["data"]["chapters"]
    assert len(chapters) == 1
    assert chapters[0]["title"] == "The Reunion"

    # 10. Scene intelligence APIs expose the approved scene
    r = await client.get(f"/v1/stories/{sid}/timeline", headers=H)
    assert r.status_code == 200
    timeline = r.json()["data"]["scenes"]
    assert len(timeline) == 1
    assert timeline[0]["id"] == scene_id
    assert timeline[0]["goal"] == "Mira wants Aiden to tell the truth."
    assert timeline[0]["time_anchor"] == "night of the coronation"
    assert timeline[0]["sensory_palette"]["sight"] == 4
    assert "Broken pact" in timeline[0]["plot_thread_names"]

    r = await client.get(f"/v1/stories/{sid}/revelations", headers=H)
    assert r.status_code == 200
    revelation = r.json()["data"]["revelations"][0]
    assert revelation["scene_id"] == scene_id
    assert revelation["reader_knows"] is True

    r = await client.get(f"/v1/stories/{sid}/weave", headers=H)
    assert r.status_code == 200
    weave = r.json()["data"]
    broken = next(t for t in weave["threads"] if t["name"] == "Broken pact")
    assert broken["cells"][0]["scene_id"] == scene_id

    r = await client.get(f"/v1/stories/{sid}/voice", headers=H)
    assert r.status_code == 200
    profiles = r.json()["data"]["profiles"]
    assert any(p["sample_count"] > 0 for p in profiles)

    # 10. Graph view returns nodes (chapter + any new characters)
    r = await client.get(f"/v1/stories/{sid}/graph/view", headers=H)
    assert r.status_code == 200
    view = r.json()["data"]
    assert "nodes" in view and "links" in view
    assert any(n["kind"] == "chapter" for n in view["nodes"])

    # 11. Export markdown
    r = await client.get(f"/v1/stories/{sid}/export/markdown", headers=H)
    assert r.status_code == 200
    assert "The Reunion" in r.text

    # 12. Story check (fallback returns a low-severity placeholder)
    chapter_id = chapters[0]["id"]
    r = await client.post(f"/v1/stories/{sid}/check", json={"chapter_id": chapter_id, "pass_type": "dialogue"}, headers=H)
    assert r.status_code == 200
    rep = r.json()["data"]
    assert rep["pass_type"] == "dialogue"
    assert "findings" in rep
    assert "severity_buckets" in rep


@pytest.mark.asyncio
async def test_auth_required(client):
    r = await client.get("/v1/stories")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_two_users_isolated(client):
    # User A creates a story
    a = await client.post("/v1/auth/signup", json={"email": "a@example.com", "password": "password1", "display_name": "A"})
    Ha = {"Authorization": f"Bearer {a.json()['data']['tokens']['access_token']}"}
    s = await client.post("/v1/stories", json={"title": "A's story"}, headers=Ha)
    sid = s.json()["data"]["story"]["id"]

    # User B tries to access it
    b = await client.post("/v1/auth/signup", json={"email": "b@example.com", "password": "password1", "display_name": "B"})
    Hb = {"Authorization": f"Bearer {b.json()['data']['tokens']['access_token']}"}
    r = await client.get(f"/v1/stories/{sid}", headers=Hb)
    assert r.status_code == 404  # masked as not-found, not leaked as forbidden


@pytest.mark.asyncio
async def test_llm_settings_roundtrip(client):
    r = await client.post("/v1/auth/signup", json={"email": "ll@example.com", "password": "password1", "display_name": "L"})
    H = {"Authorization": f"Bearer {r.json()['data']['tokens']['access_token']}"}

    # Choosing your own AI provider is a BYOK-plan feature now; upgrade this user
    # so the config round-trip is allowed (free/dev_ai are blocked by design).
    from app.core import plans
    from app.db.models import User
    from app.db.session import SessionLocal
    from app.services import billing_service
    async with SessionLocal() as db:
        u = await db.get(User, r.json()["data"]["user"]["id"])
        await billing_service.set_plan(db, u, plans.BYOK, status=plans.STATUS_ACTIVE)
        await db.commit()

    # Save settings
    lane = {
        "provider": "openai",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "embed_model": "text-embedding-3-small",
        "api_key": "sk-test-not-real",
    }
    r = await client.put("/v1/llm/config", json={
        "creative": lane,
        "technical": lane,
        "embedding": lane,
    }, headers=H)
    assert r.status_code == 200
    s = r.json()["data"]
    assert s["creative"]["provider"] == "openai"
    assert s["creative"]["has_api_key"] is True

    # Read back
    r = await client.get("/v1/llm/config", headers=H)
    assert r.json()["data"]["creative"]["model"] == "gpt-4o-mini"
