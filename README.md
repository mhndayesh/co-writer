# G-Ink Novel Studio

Full-stack AI-powered writing studio. A from-scratch implementation of the Story Forge product vision (`Story_Forge_Docs.md`); the original single-file React prototype (`story_forge.jsx`) is kept in the repo for reference only — it is not a runtime dependency.

## What it is

- **Six writer-facing tabs** — Flow Writing, Chapters, Characters, Your World, Story Map, Story Check
- **Six production stages** — Foundation → Characters → Plot → Write → Produce → Review (same data, structured nav)
- **Multi-user** with per-user accounts and encrypted per-user LLM API keys
- **LLM-agnostic with split routing** — defaults to **LM Studio** (local); per-user switch to OpenAI, Anthropic, OpenRouter, or Google Gemini, and route creative work vs technical work to different models (see [Routing modes](#routing-modes--split-creative-work-from-technical-work))
- **Writer-first Flow** — free-write → AI polish (or skip it with "use my writing as-is") → it auto-files characters, relationships, locations, factions, themes, events, and plot threads
- **Three graph layers** —
  - Front-end **Story Map** (react-force-graph-2d)
  - Backend **Neo4j knowledge graph** projection
  - **Graph-RAG** (Qdrant vectors + Neo4j subgraphs) so the AI reads the graph during generation
- **Light & dark themes**, and a blocking progress overlay while AI runs

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
cp .env.example .env   # only needed once; run.sh also auto-generates secrets on first run
./run.sh
```

`./run.sh` installs frontend deps on first run, generates `.env` secrets if missing, applies DB migrations, then starts the backend on :8080 and frontend on :3000 with tagged logs. Ctrl+C stops both. SQLite by default — no Docker required. (See [RUN.md](RUN.md) for all run options.)

### Option A — Docker (full stack incl. Neo4j + Qdrant)

```bash
cp .env.example .env
# Generate the two secrets the .env asks for
python -c "import secrets; print('JWT_SECRET=' + secrets.token_urlsafe(64))"
python -c "from cryptography.fernet import Fernet; print('LLM_KEY_ENCRYPTION_KEY=' + Fernet.generate_key().decode())"
# Paste the values into .env, then:
docker compose up -d
```

Open http://localhost:3000 — sign up — create a story.

By default, the API will try to reach LM Studio at `http://host.docker.internal:1234/v1`. Start LM Studio with any chat model loaded and Server Mode enabled. If LM Studio isn't running, the app still works with a deterministic fallback so you can explore the UI.

### Option B — Local dev (without Docker)

Terminal 1 — services:
```bash
docker compose up -d postgres neo4j qdrant
```

Terminal 2 — backend:
```bash
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -e .[dev]
alembic upgrade head
uvicorn app.main:app --reload --port 8080
```

Terminal 3 — frontend:
```bash
cd apps/web
npm install --legacy-peer-deps
npm run dev
```

## Switching LLM providers

In the UI: Settings → Routing mode + provider slots.

Providers: **LM Studio** (default, local `http://localhost:1234/v1`), **OpenAI** (`sk-...`), **Anthropic** (`sk-ant-...`, Claude Sonnet 4.5 default), **OpenRouter** (one key, namespaced models like `anthropic/claude-3.5-sonnet`), and **Google Gemini** (`gemini-2.0-flash`, with embeddings via `text-embedding-004`). Keys are encrypted at rest with Fernet using `LLM_KEY_ENCRYPTION_KEY`.

### Routing modes — split creative work from technical work

Different parts of the studio can run on different models. Pick a mode in Settings:

| Mode | Behavior |
|---|---|
| **Single model** | One provider/model handles everything (the default). |
| **Split creative/technical** | **Creative** slot drives prose work — Flow Polish, Writing Companion, Story Check. **Technical** slot drives structured extraction/filing. A dedicated **Embedding** slot handles Graph-RAG vectors. |
| **Custom per-task** | Choose a provider/model for each task individually (Flow Polish, Writing Companion, Story Check, Flow Extract). Unset tasks fall back to their category, then to the default. |

So you can, e.g., keep cheap structured "inserting" on a local LM Studio model while sending creative writing to a stronger cloud model — or any mix.

**Resolution order (custom mode):** `task:<page>` → category (creative/technical) → default profile.

**Embeddings** always resolve to an embed-capable provider. Anthropic and OpenRouter have no embeddings API, so selecting one silently falls back to local LM Studio for vectors — your story text isn't sent to a cloud embedder unless you point the Embedding slot at one (OpenAI, Gemini, or LM Studio).

Every AI run is logged to the `llm_runs` table with its provider + task, so you can audit which model handled what.

## Repo layout

```
apps/
  api/          FastAPI backend
  web/          Next.js frontend
packages/
  schemas/      Shared JSON schemas
docker-compose.yml
Story_Forge_Docs.md   ← original product vision (historical reference)
story_forge.jsx       ← original single-file prototype (reference only)
```

See [Story_Forge_Docs.md](Story_Forge_Docs.md) for the original product vision (the *why*), [RUN.md](RUN.md) for run options, and [CLAUDE.md](CLAUDE.md) for the architecture quick-tour (the current *how*).
