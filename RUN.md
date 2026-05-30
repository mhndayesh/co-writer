# Running Co-Writer — by G-Ink Studio

## Prerequisites

- **Python 3.11+**
- **Node.js 20+** and **npm**
- **Docker** (optional — `run.sh` uses it to start Qdrant + Neo4j automatically; the app works without them in degraded mode)
- **LM Studio** running with any chat model loaded (optional — the app degrades to a deterministic fallback if unreachable)

## Path 0 — One command (recommended)

```bash
./run.sh
```

`run.sh` does everything in order:

1. Checks the Python venv exists (errors with setup instructions if not)
2. Auto-generates `apps/api/.env` with fresh `JWT_SECRET` + `LLM_KEY_ENCRYPTION_KEY` on first run
3. Appends missing `QDRANT_URL` / `NEO4J_URI` lines to an existing `.env` (idempotent)
4. Starts **Qdrant** (`gink-qdrant` on :6333) and **Neo4j** (`gink-neo4j` on :7687/:7474) via Docker — skips if already running, skips silently if Docker is unavailable
5. Applies DB migrations (`alembic upgrade head`) — idempotent
6. Starts the **backend** on **:8080** and **frontend** on **:3000** with `[api]`/`[web]`-tagged logs
7. **Ctrl+C** stops backend, frontend, and the Docker containers

First-time Python setup (once):
```bash
cd apps/api && python3 -m venv .venv && ./.venv/bin/pip install -e .[dev] && cd ../..
./run.sh
```

Services started by `run.sh`:
- http://localhost:3000 — Co-Writer frontend
- http://localhost:8080 — API
- http://localhost:6333 — Qdrant (vector store for RAG)
- http://localhost:7474 — Neo4j browser (`neo4j` / `gink_dev_password`)

## Path A — Docker compose (full stack)

```bash
cp .env.example .env
python3 -c "import secrets; print('JWT_SECRET=' + secrets.token_urlsafe(64))"
python3 -c "from cryptography.fernet import Fernet; print('LLM_KEY_ENCRYPTION_KEY=' + Fernet.generate_key().decode())"
# Paste both into .env, then:
docker compose up -d
docker compose logs -f api
```

- Web: http://localhost:3000 · API: http://localhost:8080
- Neo4j: http://localhost:7474 (`neo4j` / `gink_dev_password`)
- Qdrant: http://localhost:6333/dashboard

LM Studio on the host is reached as `http://host.docker.internal:1234/v1` from the API container.

## Path B — Local dev (Docker only for data stores)

```bash
# Terminal 1 — data stores
docker compose up -d postgres neo4j qdrant

# Terminal 2 — backend
cd apps/api
python3 -m venv .venv && source .venv/bin/activate
pip install -e .[dev]
export DATABASE_URL=postgresql+asyncpg://gink:gink_dev@localhost:5432/gink
export QDRANT_URL=http://localhost:6333
export NEO4J_URI=bolt://localhost:7687
export NEO4J_PASSWORD=gink_dev_password
export JWT_SECRET=$(python3 -c 'import secrets;print(secrets.token_urlsafe(64))')
export LLM_KEY_ENCRYPTION_KEY=$(python3 -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())')
alembic upgrade head
uvicorn app.main:app --reload --port 8080

# Terminal 3 — frontend
cd apps/web && npm install --legacy-peer-deps && npm run dev
```

## Path C — Zero-dependency (SQLite + fallback LLM)

Run without any external services. Neo4j/Qdrant unset → Story Map derives from SQLite, RAG returns empty (graceful); no LLM → deterministic fallback (all responses succeed, AI features return placeholder text). This is what `run.sh` does on a machine without Docker.

## Running the tests

```bash
cd apps/api
.venv/bin/pytest -q                              # whole suite (10 tests)
.venv/bin/pytest tests/test_llm_routing.py -v    # provider-routing tests
.venv/bin/pytest tests/test_smoke.py -v          # full flow smoke tests
```

Smoke tests run against an unreachable LM Studio URL, forcing the fallback provider — they exercise every degraded path without any external services.

## Manual smoke (UI)

1. http://localhost:3000 → **Get started** → sign up. Create a story.
2. **Settings** → confirm **Use the same model for everything**, provider **LM Studio**. Click **Test**.
3. Open the story → **Flow Writing**.
   - Write a raw scene, then **Shape this into a scene →** (AI polish) or **Use my writing as-is →**.
   - Review the extracted entities — characters, relationships, locations, factions, themes, threads, scenes, revelations.
   - **Approve & save**. Everything is filed automatically.
4. **Chapters** — your chapter is there; try the **Writing Companion**.
5. **Characters** — check that character status + arc updates from the scene carried through.
6. **Timeline** — scenes sorted by `time_sort_key` (chronological) or reading order.
7. **Threads** — Plot Threads list + Weave grid (which threads touch which scenes).
8. **Continuity Radar** — click **Reindex story vectors**, then query anything (e.g. a character name) to see the Graph-RAG context the AI would receive.
9. **Story Map**, **Story Check**, **Export** (MD/DOCX/JSON).

## Provider switching & routing

Settings → fill the provider slot(s), **Test** each, **Save settings**.

| Lane | Used for |
|---|---|
| **Creative** | Flow Polish, Writing Companion, Story Check |
| **Technical** | Structured extraction and filing |
| **Embedding** | Graph-RAG vectors (Qdrant) |

**Use the same model for everything** sets all three lanes identically. Split lanes to use, e.g., a cheap local model for extraction and a stronger cloud model for creative writing.

Providers: **LM Studio** (default, local :1234), **OpenAI**, **Anthropic**, **OpenRouter**, **Google Gemini**. Anthropic/OpenRouter have no embeddings API → Embedding lane falls back to local LM Studio. Keys encrypted at rest via Fernet (`LLM_KEY_ENCRYPTION_KEY`).

To audit routing, run a polish and an extract, then check the `llm_runs` table — each row shows the `provider`, `model`, and `page` that handled it.
