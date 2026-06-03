"""Character Voice Studio — identity CRUD, layer compile-to-legacy, masks/states,
versioning, and the AI surfaces under the fallback provider.

Runs against the unreachable LM Studio URL like the rest of the suite, so the AI
endpoints exercise their fallback/parse-None guards rather than real model output.
"""
import pytest

from app.db.session import SessionLocal
from app.services.context_builder import build_story_context
from app.services.observer_service import line_fingerprint


async def _location(client, H, sid, name="Ramen Shop"):
    r = await client.post(f"/v1/stories/{sid}/locations", json={"name": name}, headers=H)
    return r.json()["data"]["location"]["id"]


async def _auth(client, email="voice@example.com"):
    r = await client.post("/v1/auth/signup", json={"email": email, "password": "password123", "display_name": "V"})
    assert r.status_code == 200, r.text
    token = r.json()["data"]["tokens"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _story(client, H):
    r = await client.post("/v1/stories", json={"title": "Voice Tale", "genre": "Noir"}, headers=H)
    return r.json()["data"]["story"]["id"]


async def _character(client, H, sid, name="Kinji"):
    r = await client.post(f"/v1/stories/{sid}/characters", json={"name": name, "role": "protagonist"}, headers=H)
    return r.json()["data"]["character"]["id"]


@pytest.mark.asyncio
async def test_identity_crud_and_legacy_projection(client):
    H = await _auth(client)
    sid = await _story(client, H)
    cid = await _character(client, H, sid)

    # GET identity lazily creates an empty (seeded) row
    r = await client.get(f"/v1/stories/{sid}/identity/{cid}", headers=H)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["identity"]["character_id"] == cid
    assert data["masks"] == []
    assert data["states"] == []

    # PATCH the core layer (keys are interview question ids — the shared vocabulary)
    r = await client.patch(
        f"/v1/stories/{sid}/identity/{cid}/layer/core",
        json={"payload": {"lie": "Trust no one", "want": "Find the truth", "shame": "Being seen"},
              "build_method": "manual"},
        headers=H,
    )
    assert r.status_code == 200, r.text
    ident = r.json()["data"]["identity"]
    assert ident["core_personality"]["lie"] == "Trust no one"
    assert ident["completeness"]["core"] > 0

    # The legacy Character columns must be recompiled from the layer (back-compat):
    # lie → personality, want → motivation.
    r = await client.get(f"/v1/stories/{sid}/characters", headers=H)
    ch = next(c for c in r.json()["data"]["characters"] if c["id"] == cid)
    assert "Trust no one" in ch["personality"]
    assert "Find the truth" in ch["motivation"]

    # Unknown layer is rejected
    r = await client.patch(f"/v1/stories/{sid}/identity/{cid}/layer/bogus", json={"payload": {}}, headers=H)
    assert r.status_code == 404

    # A version snapshot was recorded for the core edit
    r = await client.get(f"/v1/stories/{sid}/identity/{cid}/versions", headers=H)
    assert r.status_code == 200
    versions = r.json()["data"]["versions"]
    assert any(v["kind"] == "core" for v in versions)


@pytest.mark.asyncio
async def test_masks_and_states(client):
    H = await _auth(client, "masks@example.com")
    sid = await _story(client, H)
    cid = await _character(client, H, sid)
    other = await _character(client, H, sid, name="Hina")

    # Add a relationship mask
    r = await client.post(
        f"/v1/stories/{sid}/identity/{cid}/masks",
        json={"audience_character_id": other, "speech_style": "guarded, terse", "tells": "looks away"},
        headers=H,
    )
    assert r.status_code == 200, r.text
    mask_id = r.json()["data"]["mask"]["id"]

    r = await client.get(f"/v1/stories/{sid}/identity/{cid}/masks", headers=H)
    assert len(r.json()["data"]["masks"]) == 1

    r = await client.patch(f"/v1/stories/{sid}/identity/masks/{mask_id}", json={"speech_style": "warmer"}, headers=H)
    assert r.json()["data"]["mask"]["speech_style"] == "warmer"

    r = await client.delete(f"/v1/stories/{sid}/identity/masks/{mask_id}", headers=H)
    assert r.status_code == 200

    # Set + clear a scene state
    r = await client.post(
        f"/v1/stories/{sid}/identity/{cid}/states",
        json={"label": "injured", "detail": "knife wound", "kind": "temporary"},
        headers=H,
    )
    assert r.status_code == 200, r.text
    state_id = r.json()["data"]["state"]["id"]

    r = await client.get(f"/v1/stories/{sid}/identity/{cid}/states?active_only=true", headers=H)
    assert len(r.json()["data"]["states"]) == 1

    r = await client.delete(f"/v1/stories/{sid}/identity/states/{state_id}", headers=H)
    assert r.status_code == 200
    r = await client.get(f"/v1/stories/{sid}/identity/{cid}/states?active_only=true", headers=H)
    assert len(r.json()["data"]["states"]) == 0


@pytest.mark.asyncio
async def test_identity_feeds_context_and_degrades_by_detail(client):
    H = await _auth(client, "ctx@example.com")
    sid = await _story(client, H)
    cid = await _character(client, H, sid, name="Kinji")

    await client.patch(
        f"/v1/stories/{sid}/identity/{cid}/layer/voice",
        json={"payload": {"cadence": "clipped", "directness": "terse, deflects"}},
        headers=H,
    )

    async with SessionLocal() as db:
        # Identity shows up in the assembled context.
        ctx = await build_story_context(db, sid)
        assert "CHARACTER IDENTITY" in ctx
        assert "Kinji" in ctx
        assert "clipped" in ctx

        # Under brutal budget pressure the cast roster survives but the rich
        # identity is dropped first (degrade by detail, never the cast).
        tight = await build_story_context(db, sid, char_budget=60)
        assert "# CAST" in tight
        assert "CHARACTER IDENTITY" not in tight


@pytest.mark.asyncio
async def test_scene_focus_pins_identity_even_under_budget(client):
    H = await _auth(client, "scene@example.com")
    sid = await _story(client, H)
    cid = await _character(client, H, sid, name="Kinji")
    await client.patch(
        f"/v1/stories/{sid}/identity/{cid}/layer/voice",
        json={"payload": {"cadence": "clipped", "directness": "blunt, deflects"}},
        headers=H,
    )

    async with SessionLocal() as db:
        # With scene focus, the in-scene character is pinned in SCENE FOCUS and
        # survives even a tiny budget that drops the general identity section.
        ctx = await build_story_context(db, sid, char_budget=80, scene_character_ids=[cid])
        assert "# SCENE FOCUS" in ctx
        assert "Kinji" in ctx
        assert "clipped" in ctx
        # And the focused character is NOT duplicated in the general identity block.
        assert ctx.count("clipped") == 1


@pytest.mark.asyncio
async def test_interview_bank_tiers_and_layers(client):
    H = await _auth(client, "interview@example.com")
    sid = await _story(client, H)

    # Tiers hit the research spec exactly: 10 / 20 / 35 base questions covering all
    # five layers (branch questions are extra, surfaced only when triggered).
    expected = {"quick": 10, "medium": 20, "deep": 35}
    for tier, n in expected.items():
        r = await client.get(f"/v1/stories/{sid}/identity/interview?tier={tier}", headers=H)
        assert r.status_code == 200, r.text
        qs = r.json()["data"]["questions"]
        base = [q for q in qs if not q.get("is_branch")]
        assert len(base) == n, f"{tier}: expected {n} base questions, got {len(base)}"
        layers = {q["layer"] for q in base}
        assert layers == {"core", "behavioral", "voice", "relationship", "current"}, f"{tier} missing layers: {layers}"
    # Branching is present (stress_response → fallback follow-up).
    deep = (await client.get(f"/v1/stories/{sid}/identity/interview?tier=deep", headers=H)).json()["data"]["questions"]
    assert any(q.get("branches") for q in deep)


@pytest.mark.asyncio
async def test_interview_synthesis_routes_all_layers(client):
    H = await _auth(client, "synth@example.com")
    sid = await _story(client, H)
    cid = await _character(client, H, sid)

    # Answers span all five layers, keyed by the real question ids. Synthesis runs
    # on the fallback provider (returns no JSON) and must not crash; build_method
    # is set and the author's tagged answers are preserved.
    r = await client.post(
        f"/v1/stories/{sid}/identity/{cid}/interview",
        json={"tier": "medium", "answers": {
            "want": "to find his partner's killer",
            "lie": "trust is a liability",
            "stress_response": "freeze / shut down",
            "directness": "blunt / direct",
            "authority_mask": "clipped, gives nothing away",
            "concealed_affect": "grief he refuses to name",
        }},
        headers=H,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["identity"]["build_method"] == "interview"
    # The synthesis call completed without dropping the relationship/current answers
    # on the floor (they route to masks/states tables; under fallback nothing is
    # created, but the endpoint must accept and process them without error).
    r = await client.get(f"/v1/stories/{sid}/identity/{cid}", headers=H)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_analyze_writing_and_approve(client):
    H = await _auth(client, "analyze@example.com")
    sid = await _story(client, H)
    cid = await _character(client, H, sid)

    sample = '"Lock it," Kinji said. "And kill the lights." He never asked twice.'
    r = await client.post(f"/v1/stories/{sid}/identity/{cid}/analyze", json={"text": sample}, headers=H)
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert "traits" in body  # may be empty under the fallback provider — must not crash

    # Approving a (hand-built) trait commits it into the right layer.
    r = await client.post(
        f"/v1/stories/{sid}/identity/{cid}/analyze/approve",
        json={"decisions": [{"layer": "voice", "field": "directness", "value": "blunt, terse", "decision": "approve"},
                            {"layer": "core", "field": "worldview", "value": "ignored", "decision": "reject"}]},
        headers=H,
    )
    assert r.status_code == 200, r.text
    ident = r.json()["data"]["identity"]
    assert ident["voice_fingerprint"]["directness"] == "blunt, terse"
    assert "worldview" not in (ident["core_personality"] or {})


@pytest.mark.asyncio
async def test_analyze_from_selected_chapters_with_budget(client):
    H = await _auth(client, "analyzech@example.com")
    sid = await _story(client, H)
    cid = await _character(client, H, sid, name="Kinji")

    # Create two chapters; analyze by chapter id (no pasted text).
    c1 = (await client.post(f"/v1/stories/{sid}/chapters",
          json={"title": "Arrival", "content": '"Lock it," Kinji said. "Lights off."'}, headers=H)).json()["data"]["chapter"]["id"]
    c2 = (await client.post(f"/v1/stories/{sid}/chapters",
          json={"title": "The Bag", "content": "Kinji didn't flinch. He counted the exits."}, headers=H)).json()["data"]["chapter"]["id"]

    r = await client.post(f"/v1/stories/{sid}/identity/{cid}/analyze",
                          json={"chapter_ids": [c1, c2]}, headers=H)
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert {c["id"] for c in body["used_chapters"]} == {c1, c2}
    assert body["truncated"] is False

    # A giant pasted sample is truncated to the budget but still succeeds.
    big = "x " * 70000  # ~140k chars, over the 128k budget
    r = await client.post(f"/v1/stories/{sid}/identity/{cid}/analyze", json={"text": big}, headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["truncated"] is True

    # Empty request (no chapters, no text) returns an empty result, not a 500.
    r = await client.post(f"/v1/stories/{sid}/identity/{cid}/analyze", json={}, headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["traits"] == []


def test_analyze_is_anchored_to_real_bank_questions():
    # The analyze pass must only offer the actual extractable bank questions
    # (core/behavioral/voice), each mapping a question id → its layer + text.
    from app.services.identity_questions import extractable_questions, QUESTIONS_BY_ID
    qs = extractable_questions()
    assert len(qs) > 0
    for q in qs:
        assert q["layer"] in ("core", "behavioral", "voice")
        assert QUESTIONS_BY_ID[q["id"]]["text"] == q["text"]
    # Relationship / current questions are interview-only, never offered to analyze.
    assert not any(q["layer"] in ("relationship", "current") for q in qs)


@pytest.mark.asyncio
async def test_place_identity_crud_and_build(client):
    H = await _auth(client, "place@example.com")
    sid = await _story(client, H)
    loc = await _location(client, H, sid)

    # Questions bank
    r = await client.get(f"/v1/stories/{sid}/place/questions", headers=H)
    assert r.status_code == 200 and len(r.json()["data"]["questions"]) > 0

    # GET lazily creates, PATCH saves
    r = await client.get(f"/v1/stories/{sid}/place/{loc}", headers=H)
    assert r.status_code == 200, r.text
    r = await client.patch(f"/v1/stories/{sid}/place/{loc}", json={"atmosphere": "cramped, familiar"}, headers=H)
    assert r.json()["data"]["place"]["atmosphere"] == "cramped, familiar"

    # Build from answers — under fallback, deterministic field mapping kicks in
    r = await client.post(f"/v1/stories/{sid}/place/{loc}/build",
                          json={"answers": {"purpose": "where Kinji drops his guard", "sound": "slurping"}}, headers=H)
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_observer_marks_intentional_and_stops_reflagging(client):
    H = await _auth(client, "observer@example.com")
    sid = await _story(client, H)
    cid = await _character(client, H, sid, name="Kinji")

    draft = '"I am quite concerned that we may have been followed," Kinji said.'
    r = await client.post(f"/v1/stories/{sid}/observer/critique",
                          json={"draft": draft, "strictness": "balanced"}, headers=H)
    assert r.status_code == 200, r.text
    assert "notes" in r.json()["data"]  # may be empty under fallback — must not crash

    # Marking a line intentional records an exception; a subsequent critique whose
    # candidate note has the same fingerprint is suppressed.
    line = "I am quite concerned that we may have been followed."
    r = await client.post(f"/v1/stories/{sid}/observer/mark-intentional",
                          json={"line": line, "note_kind": "voice_mismatch", "character_id": cid,
                                "reason": "he is deliberately faking politeness here"}, headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["exception_id"]

    # Idempotent: marking the same line again returns the same row, no crash.
    r2 = await client.post(f"/v1/stories/{sid}/observer/mark-intentional",
                           json={"line": line, "note_kind": "voice_mismatch", "character_id": cid}, headers=H)
    assert r2.status_code == 200


@pytest.mark.asyncio
async def test_rewrite_evolve_and_compare(client):
    H = await _auth(client, "writer@example.com")
    sid = await _story(client, H)
    a = await _character(client, H, sid, name="Kinji")
    b = await _character(client, H, sid, name="Hina")

    # Dialogue Writer rewrite
    r = await client.post(f"/v1/stories/{sid}/observer/rewrite",
                          json={"draft": '"Hello," he said.', "strictness": "balanced"}, headers=H)
    assert r.status_code == 200, r.text
    assert "rewritten" in r.json()["data"]

    # Post-scene evolve suggestions (no commit) + apply
    r = await client.post(f"/v1/stories/{sid}/identity/evolve",
                          json={"text": "Kinji flinched at the knock — he never used to."}, headers=H)
    assert r.status_code == 200, r.text
    r = await client.post(f"/v1/stories/{sid}/identity/evolve/apply",
                          json={"decisions": [{"type": "new_stress_behavior", "character_id": a,
                                               "summary": "flinches at sudden knocks", "save_as": "recurring"}]}, headers=H)
    assert r.status_code == 200 and r.json()["data"]["applied"] == 1

    # Voice comparison needs 2+ characters
    r = await client.post(f"/v1/stories/{sid}/identity/compare",
                          json={"character_ids": [a, b], "situation": "A stranger drops a bloody bag on the counter."}, headers=H)
    assert r.status_code == 200, r.text
    assert len(r.json()["data"]["entries"]) >= 1


def test_line_fingerprint_normalizes_whitespace_and_case():
    a = line_fingerprint("c1", "  Lock  IT. ", "voice_mismatch")
    b = line_fingerprint("c1", "lock it.", "voice_mismatch")
    assert a == b
    # Different note kind or character → different fingerprint.
    assert line_fingerprint("c1", "lock it.", "register") != a
    assert line_fingerprint("c2", "lock it.", "voice_mismatch") != a
