# Co-Writer — by G-Ink Studio

Your AI co-writer. Write freely; it polishes the prose, files every character, place, faction, theme, plot thread, scene, and revelation automatically — and watches every continuity thread so you never lose the story.

Built as a full-stack implementation of the Story Forge product vision (`Story_Forge_Docs.md`); the original single-file React prototype (`story_forge.jsx`) is kept for reference only.

## What it does

- **Flow Writing** — free-write → AI polish → structured extraction → one-click approve. Every chapter auto-files:
  - Characters (new ones created, existing ones updated — status changes like death propagate, arc notes accumulate; same-named cast members disambiguated by stable id so the wrong record is never mutated)
  - Character relationships (created on first mention, updated in place on repeat)
  - Locations, factions, themes, events
  - Plot threads (status evolves: open → paid_off / abandoned across chapters)
  - Scene cards with beat, goal, conflict, outcome, POV, location, time anchor, sensory palette
  - Revelations / information ledger (who knows what, and does the reader?)
  - Voice fingerprints (deterministic per-character dialogue stats rebuilt after every approve)
- **Language Enhancer** — improve prose quality without changing the story; detects language automatically
- **Writing Companion** — Graph-RAG-powered scene drafting from a plain instruction
- **Character Voice Studio** (Narrative Fidelity Engine) — a layer above the Story Engine for *how the story feels on the page*:
  - **5-layer character identity** — Core Personality, Behavioral Patterns, Voice Fingerprint, Relationship Masks (per-audience speech), Current State (scene-scoped)
  - **Two build methods** — Analyze existing writing (AI proposes traits with confidence + source excerpts; you approve each) or a branching Guided Interview (Quick / Medium / Deep)
  - **Place Identity** — atmosphere, sensory palette, spatial layout, symbolic motif per location
  - **Narrative Observer** — line-level critique of a draft (voice mismatch, wrong emotion, contradicts-habit, ignores-place …) with Apply / Edit / Ignore / Mark-intentional; marking a line intentional stops it being re-flagged
  - **Dialogue Writer** — rewrite a draft so everyone sounds like themselves
  - **Evolve** — after a scene, decide what each change becomes (temporary / recurring / permanent) so one-offs don't pollute the profile
  - **Voice Comparison** — same situation, side-by-side responses to check two characters feel distinct
  - All of it feeds the normal prose pipeline automatically (see *What the AI sees*); a **Scene setup** picker on Flow polish pins the in-scene cast's full identity so they're never trimmed
- **Three top-level views** — Flow, Studio, and Voice (sidebar toggle), all over the same story data
- **Six writer-facing tabs** (Flow view) — Flow Writing, Chapters, Characters, Your World, Story Map, Story Check
- **Six production stages** (Studio view) — Foundation → Characters → Plot → Write → Produce → Review
- **Timeline & Weave** — scenes sorted by chronological `time_sort_key`; Plot Weave grid showing which threads touch which scenes
- **Continuity Radar** — inspect exactly what the AI sees (Graph-RAG context) for any query, with vector reindex
- **Publishing platform** — publish stories publicly, manage chapters for readers, reader comments
- **Billing & subscriptions** — Stripe-powered plan tiers; per-user AI entitlements
- **Multi-user** with per-user accounts (Clerk auth), encrypted per-user LLM API keys
- **LLM-agnostic with a simple router** — defaults to **LM Studio** (local); per-user switch to OpenAI, Anthropic, OpenRouter, or Google Gemini, with creative / technical / embedding lanes routed separately
- **Three graph layers** — front-end Story Map (react-force-graph-2d), Neo4j knowledge graph, Graph-RAG (Qdrant + Neo4j subgraphs)
- **Light & dark themes**, blocking progress overlay while AI runs

## Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI · async SQLAlchemy 2.0 · Alembic · ARQ (background jobs) |
| Auth | Clerk (JWT/JWKS) · bcrypt legacy path · Fernet for secret encryption |
| DB | PostgreSQL (prod) / SQLite (dev) |
| Graph | Neo4j 5 |
| Vector | Qdrant (single shared collection `gink_chunks`, per-story payload filter) |
| Frontend | Next.js 15 · React 19 · TypeScript · Tailwind · Zustand · TanStack Query |

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

Every LLM call is assembled with a priority-packed context budget (~7k tokens). The most load-bearing sections are never dropped; older chapters/scenes are trimmed when a manuscript grows long:

| Section | Priority | Notes |
|---|---|---|
| **WORLD** | always kept | genre, logline, setting, rules, lore |
| **CAST** | always kept | every character with role, status, personality, arc; stable `[id:…]` included for extract calls so same-named characters are never confused |
| **SCENE FOCUS** | always kept | the in-scene cast's *full* Voice Studio identity (+ masks + state) and the scene's place identity — only present when a Scene setup is given; never trimmed |
| **GRAPH CONTEXT** | always kept | Qdrant vector hits + Neo4j 1-hop subgraph (when running) |
| **PLOT THREADS** | high | status (open/paid_off/abandoned) |
| **CHAPTERS** | high | summaries, most recent 40 kept |
| **RELATIONSHIPS** | medium | |
| **THEMES / LOCATIONS / FACTIONS** | medium | |
| **REVELATIONS** | lower | most recent 60 |
| **SCENES** | lower | most recent 80 beat cards with time key, POV, threads |
| **RELATIONSHIP MASKS** | lower | per-audience speech style (Voice Studio) — degrades by detail |
| **CHARACTER IDENTITY / PLACE IDENTITY** | lower | qualitative voice/behavior layers + place atmosphere — dropped before the cast roster |
| **VOICE FINGERPRINTS** | lowest | per-character dialogue stats (deterministic) |

A new chapter's AI always knows: which characters are dead, how arcs have evolved, what the timeline numbers look like, which threads are open vs resolved — and, when you set a Scene setup, the complete voice/behavior of everyone in the scene. Rich Voice Studio detail degrades first under budget pressure; the cast roster is never dropped.

## Model routing

Settings → provider slots.

| Lane | Used for |
|---|---|
| **Creative** | Flow Polish, Writing Companion, Story Check |
| **Technical** | Structured extraction and filing |
| **Embedding** | Graph-RAG vectors (Qdrant) |

Providers: **LM Studio** (default, local), **OpenAI**, **Anthropic**, **OpenRouter**, **Google Gemini**. Keys encrypted at rest. Anthropic / OpenRouter → embedding falls back to local LM Studio (they have no embeddings API).

Every AI run is logged to `llm_runs` with provider, model, page, timing, and token counts — full audit trail.

## Repo layout

```
apps/
  api/          FastAPI backend
    app/
      api/v1/   REST endpoints
      core/     config, auth, idempotency, prompt safety, rate limiting
      db/       models (SQLAlchemy), schemas (Pydantic), migrations
      routers/  publishing, social, reader
      services/ flow, identity + observer (Voice Studio), graph, embedding/RAG, LLM providers, billing, …
      workers/  ARQ background worker (export, graph reconciliation cron)
  web/          Next.js frontend
    app/studio/[storyId]/voice/   Character Voice Studio (Voice view)
docker-compose.yml
Story_Forge_Docs.md   ← product vision (historical reference)
story_forge.jsx       ← single-file prototype (reference only)
```

See [CLAUDE.md](CLAUDE.md) for the architecture quick-tour and hard-won quirks. See [RUN.md](RUN.md) for run options.
