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

    # 6. Flow polish (uses fallback provider, returns plausible polished text)
    r = await client.post(f"/v1/stories/{sid}/flow/polish", json={"raw": "Aiden walked into the throne room and Mira looked angry."}, headers=H)
    assert r.status_code == 200, r.text
    polished = r.json()["data"]["polished"]
    assert polished

    # 7. Flow extract
    r = await client.post(f"/v1/stories/{sid}/flow/extract", json={"polished": polished}, headers=H)
    assert r.status_code == 200, r.text
    extract = r.json()["data"]
    assert "characters" in extract

    # 8. Approve — commit as new chapter, opt-in to any detected characters
    include = [c["name"] for c in extract["characters"] if c.get("is_new")]
    r = await client.post(f"/v1/stories/{sid}/flow/approve", json={
        "raw": "Aiden walked into the throne room and Mira looked angry.",
        "polished": polished,
        "extracted": extract,
        "include_character_names": include,
        "chapter_title": "The Reunion",
        "chapter_summary": "A tense throne-room meeting.",
    }, headers=H)
    assert r.status_code == 200, r.text
    approve = r.json()["data"]
    assert approve["version_no"] >= 1

    # 9. Chapter list shows the new chapter
    r = await client.get(f"/v1/stories/{sid}/chapters", headers=H)
    assert r.status_code == 200
    chapters = r.json()["data"]["chapters"]
    assert len(chapters) == 1
    assert chapters[0]["title"] == "The Reunion"

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
    r = await client.post(f"/v1/stories/{sid}/check", json={"chapter_id": chapter_id}, headers=H)
    assert r.status_code == 200
    rep = r.json()["data"]
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

    # Save settings
    r = await client.put("/v1/llm/settings", json={
        "provider": "openai", "base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini",
        "embed_model": "text-embedding-3-small", "api_key": "sk-test-not-real",
    }, headers=H)
    assert r.status_code == 200
    s = r.json()["data"]
    assert s["provider"] == "openai"
    assert s["has_api_key"] is True

    # Read back
    r = await client.get("/v1/llm/settings", headers=H)
    assert r.json()["data"]["model"] == "gpt-4o-mini"
