# Running G-Ink Novel Studio

## Prerequisites

- **Python 3.11+**
- **Node.js 20+** and **npm**
- **Docker** (only if you want Neo4j + Qdrant + Postgres in containers; SQLite + fallback works without)
- **LM Studio** running with any chat model loaded (optional but recommended — otherwise the studio runs in deterministic fallback mode)

## Path 0 — One command (recommended)

```bash
./run.sh
```

`run.sh` installs frontend deps on first run, generates `apps/api/.env` with fresh `JWT_SECRET` + `LLM_KEY_ENCRYPTION_KEY` if missing, applies DB migrations (`alembic upgrade head`), kills stale servers, then starts the backend on **:8080** and frontend on **:3000** with `[api]`/`[web]`-tagged logs. **Ctrl+C** stops both. SQLite by default — no Docker needed.

First-time only, if the Python venv doesn't exist yet:

```bash
cd apps/api && python3 -m venv .venv && ./.venv/bin/pip install -e .[dev] && cd ../..
./run.sh
```

## Path A — Docker compose (full stack incl. Neo4j + Qdrant)

```bash
cp .env.example .env
# Generate the two required secrets, paste into .env:
python3 -c "import secrets; print('JWT_SECRET=' + secrets.token_urlsafe(64))"
python3 -c "from cryptography.fernet import Fernet; print('LLM_KEY_ENCRYPTION_KEY=' + Fernet.generate_key().decode())"
docker compose up -d
docker compose logs -f api
```

- Web: http://localhost:3000 · API: http://localhost:8080/health
- Neo4j browser: http://localhost:7474 (`neo4j` / `gink_dev_password`)
- Qdrant dashboard: http://localhost:6333/dashboard

LM Studio on the host is reached as `http://host.docker.internal:1234/v1` from the API container.

## Path B — Local dev (Docker only for the data stores)

```bash
docker compose up -d postgres neo4j qdrant   # terminal 1

cd apps/api                                   # terminal 2
python3 -m venv .venv && source .venv/bin/activate
pip install -e .[dev]
export DATABASE_URL=postgresql+asyncpg://gink:gink_dev@localhost:5432/gink
export JWT_SECRET=$(python3 -c 'import secrets;print(secrets.token_urlsafe(64))')
export LLM_KEY_ENCRYPTION_KEY=$(python3 -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())')
alembic upgrade head
uvicorn app.main:app --reload --port 8080

cd apps/web && npm install --legacy-peer-deps && npm run dev   # terminal 3
```

## Path C — Zero-dependency (SQLite + fallback LLM)

Play with the UI without any external services. Neo4j/Qdrant unset → graph derives from SQLite, RAG degrades gracefully; no LLM → deterministic fallback. This is essentially what `run.sh` automates.

## Running the tests

```bash
cd apps/api
.venv/bin/pytest -q                              # whole suite
.venv/bin/pytest tests/test_llm_routing.py -v    # provider-routing tests only
```

`test_smoke.py` runs the full signup → story → polish → extract → approve → graph → export flow against an unreachable LM Studio URL (forcing the fallback provider). `test_llm_routing.py` asserts single/split/custom routing + embedding fallback.

## Manual smoke (UI)

1. http://localhost:3000 → **Get started** → sign up. Create a story.
2. **Settings** → confirm Routing mode **Single model**, provider **LM Studio**. Click **Test**.
3. Open the story → **Flow Writing**.
   - Write a raw scene, then **Shape this into a scene →** (AI polish) OR **Use my writing as-is →** to keep your own prose.
   - Review, then **Approve & save**. New characters, relationships, locations, factions, themes, events, and plot threads are filed **automatically** — no checkboxes.
4. **Chapters** — your scene is there; try the **Writing Companion**.
5. **Characters** — one relationship per linked character (re-approving a later chapter updates the bond in place).
6. **Story Map**, **Story Check**, **Studio view** stages, **light/dark** toggle (sidebar), **Export** (MD/DOCX/JSON).

Deleting a middle chapter preserves the gap — Flow Writing then offers to **fill the gap** or **redo** an existing chapter via the "Save as" selector.

## Provider switching & routing

Settings → pick a **Routing mode**, fill the provider slot(s), **Test** each, **Save settings**.

- **Single model** — one provider for everything.
- **Split creative/technical** — Creative slot (Polish, Writing Companion, Story Check) + Technical slot (structured extraction) + a dedicated Embedding slot.
- **Custom per-task** — a provider/model per task; unset tasks fall back to category → default.

Providers: **LM Studio**, **OpenAI**, **Anthropic**, **OpenRouter** (namespaced models like `anthropic/claude-3.5-sonnet`), **Google Gemini**. Each slot has a **Test** button + reachability badge. Embeddings always use an embed-capable provider (Anthropic / OpenRouter → fall back to local LM Studio; OpenAI / Gemini / LM Studio can embed). Keys are encrypted at rest with Fernet via `LLM_KEY_ENCRYPTION_KEY`.

To verify routing, run a creative action (Flow → polish) and a technical one (approve/extract), then check the `llm_runs` table — each row shows the provider + `page` that handled it.
