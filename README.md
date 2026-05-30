# Co-Writer — by G-Ink Studio

Your AI co-writer. Write freely; it polishes the prose, files every character, place, faction, theme, plot thread, scene, and revelation automatically — and watches every continuity thread so you never lose the story.

Built as a full-stack implementation of the Story Forge product vision (`Story_Forge_Docs.md`); the original single-file React prototype (`story_forge.jsx`) is kept for reference only.

## What it does

- **Flow Writing** — free-write → AI polish → structured extraction → one-click approve. Every chapter auto-files:
  - Characters (new ones created, existing ones updated — status changes like death propagate, arc notes accumulate)
  - Character relationships (created on first mention, updated in place on repeat)
  - Locations, factions, themes, events
  - Plot threads (status evolves: open → paid_off / abandoned across chapters)
  - Scene cards with beat, goal, conflict, outcome, POV, location, time anchor, sensory palette
  - Revelations / information ledger (who knows what, and does the reader?)
  - Voice fingerprints (deterministic per-character dialogue stats rebuilt after every approve)
- **Six writer-facing tabs** — Flow Writing, Chapters, Characters, Your World, Story Map, Story Check
- **Six production stages** — Foundation → Characters → Plot → Write → Produce → Review (same data, two nav modes)
- **Timeline & Weave** — scenes sorted by chronological `time_sort_key`; Plot Weave grid showing which threads touch which scenes
- **Continuity Radar** — inspect exactly what the AI sees (Graph-RAG context) for any query
- **Multi-user** with per-user accounts and encrypted per-user LLM API keys
- **LLM-agnostic with a simple router** — defaults to **LM Studio** (local); per-user switch to OpenAI, Anthropic, OpenRouter, or Google Gemini, with creative / technical / embedding lanes routed separately
- **Three graph layers** — front-end Story Map (react-force-graph-2d), Neo4j knowledge graph, Graph-RAG (Qdrant + Neo4j subgraphs)
- **Light & dark themes**, blocking progress overlay while AI runs

## Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI · async SQLAlchemy 2.0 · Alembic |
| DB | PostgreSQL (prod) / SQLite (dev) |
| Graph | Neo4j 5 |
| Vector | Qdrant |
| Frontend | Next.js 15 · React 19 · TypeScript · Tailwind · Zustand · TanStack Query |
| Auth | JWT (access + refresh) · bcrypt · Fernet for secret encryption |

## Quick start

### Option 0 — One command (local, simplest)

```bash
./run.sh
```

`run.sh` installs frontend deps on first run, generates `apps/api/.env` secrets if missing, applies DB migrations, starts **Qdrant** and **Neo4j** via Docker (if Docker is available), then streams the backend on **:8080** and frontend on **:3000** with tagged logs. Ctrl+C stops everything, including the Docker containers. SQLite by default — no external DB needed.

First-time Python setup (once):
```bash
cd apps/api && python3 -m venv .venv && ./.venv/bin/pip install -e .[dev] && cd ../..
./run.sh
```

### Option A — Docker (full stack)

```bash
cp .env.example .env
python3 -c "import secrets; print('JWT_SECRET=' + secrets.token_urlsafe(64))"
python3 -c "from cryptography.fernet import Fernet; print('LLM_KEY_ENCRYPTION_KEY=' + Fernet.generate_key().decode())"
# Paste both into .env, then:
docker compose up -d
```

Open http://localhost:3000 — sign up — create a story.

### Option B — Local dev (manual)

```bash
# Terminal 1 — data stores
docker compose up -d postgres neo4j qdrant

# Terminal 2 — backend
cd apps/api && python3 -m venv .venv && source .venv/bin/activate
pip install -e .[dev] && alembic upgrade head
uvicorn app.main:app --reload --port 8080

# Terminal 3 — frontend
cd apps/web && npm install --legacy-peer-deps && npm run dev
```

## What the AI sees

The context fed into every LLM call includes:

- **WORLD** — genre, logline, setting, rules, lore
- **CAST** — every character with role, status, personality, accumulated arc
- **RELATIONSHIPS** — all known character bonds with type and description
- **LOCATIONS / FACTIONS / THEMES / PLOT THREADS** (with status)
- **CHAPTERS** — summaries of prior chapters (most recent 20)
- **SCENES** — stored beat cards with `time_key`, POV, location, threads (last 60)
- **REVELATIONS** — who knows what, reader perspective
- **VOICE FINGERPRINTS** — per-character dialogue stats
- **Graph-RAG** — Qdrant vector hits + Neo4j 1-hop subgraph for the query (when Qdrant/Neo4j are running)

This means a new chapter's AI always knows: which characters are dead, how arcs have evolved, what the timeline numbers look like, and which threads are open vs resolved.

## Model routing

Settings → provider slots.

| Lane | Used for |
|---|---|
| **Creative** | Flow Polish, Writing Companion, Story Check |
| **Technical** | Structured extraction and filing |
| **Embedding** | Graph-RAG vectors |

Providers: **LM Studio** (default, local), **OpenAI**, **Anthropic**, **OpenRouter**, **Google Gemini**. Keys encrypted at rest. Anthropic / OpenRouter → embedding falls back to local LM Studio (they have no embeddings API).

Every AI run is logged to `llm_runs` with provider + task, so you can audit which model handled what.

## Repo layout

```
apps/
  api/          FastAPI backend
  web/          Next.js frontend
docker-compose.yml
Story_Forge_Docs.md   ← product vision (historical reference)
story_forge.jsx       ← single-file prototype (reference only)
```

See [CLAUDE.md](CLAUDE.md) for the architecture quick-tour, [RUN.md](RUN.md) for run options.
