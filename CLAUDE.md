# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

G-Ink Novel Studio — a full-stack AI-powered writing studio. The product spec lives in [Story_Forge_Docs.md](Story_Forge_Docs.md) and the original single-file React reference is [story_forge.jsx](story_forge.jsx). Read them when in doubt about UX intent.

Monorepo with `apps/api` (FastAPI + SQLAlchemy 2 async + Alembic) and `apps/web` (Next.js 15 App Router + React 19 + Tailwind + TanStack Query + Zustand). Optional Neo4j (graph) and Qdrant (vectors) for Graph-RAG; SQLite by default.

## Commands

| Task | Command |
|---|---|
| Run the whole stack locally | `./run.sh` (kills old uvicorn/next, runs migrations, streams `[api]`/`[web]` logs, Ctrl+C stops both) |
| First-time backend setup | `cd apps/api && python3 -m venv .venv && ./.venv/bin/pip install -e .[dev]` |
| First-time frontend setup | `cd apps/web && npm install --legacy-peer-deps` |
| Backend tests | `cd apps/api && .venv/bin/pytest -v` |
| Single test | `.venv/bin/pytest tests/test_smoke.py::test_full_flow -v` |
| New migration | `cd apps/api && .venv/bin/alembic revision --autogenerate -m "msg"` |
| Apply migrations | `cd apps/api && .venv/bin/alembic upgrade head` |
| Frontend lint | `cd apps/web && npm run lint` |
| Frontend build | `cd apps/web && npm run build` |
| Docker (full stack with Neo4j+Qdrant+Postgres) | `docker compose up -d` |

Always invoke backend tools via `apps/api/.venv/bin/<tool>` — the system Python's tools (uvicorn, alembic) shadow the venv if PATH ordering is bad (conda `(base)` is a common offender).

## Architecture

### Response envelope
**Every** API route returns `{"ok": bool, "data": any, "error": {code, message, details} | null}` via `envelope_ok(...)` / `envelope_err(...)` in [`core/errors.py`](apps/api/app/core/errors.py). The frontend's `request<T>()` in [`lib/api.ts`](apps/web/lib/api.ts) unwraps `data` and throws `ApiError` on `ok: false`. Don't return bare dicts from routes.

### LLM provider abstraction
**Every** AI call must go through `llm_service.run(db, user, page=..., system=..., user_msg=..., ...)` in [`services/llm_service.py`](apps/api/app/services/llm_service.py). Never call a provider directly from a router. The service:
- resolves the provider via `get_provider_for_page(db, user, page)` in [`services/llm/factory.py`](apps/api/app/services/llm/factory.py) — the `page` string is the routing key
- logs every call to `llm_runs` with timing/tokens/excerpts (and the resolved provider — your audit trail for which model handled which task)
- on failure, retries on the deterministic [`FallbackProvider`](apps/api/app/services/llm/fallback.py) so the UI never breaks

**Routing (simple lanes).** A user has one `user_llm_settings.lanes` JSON object with three slots: `creative`, `technical`, and `embedding`. [`services/llm/roles.py`](apps/api/app/services/llm/roles.py) maps each `page` to a category: `flow.polish`/`flow.companion`/`story_check` → **creative**, `flow.extract`/`llm.test` → **technical**, unknown → technical. `get_provider_for_page` reads the lane for that category; `get_embedding_provider` reads the embedding lane and falls back to local LM Studio if the selected provider cannot embed. The Settings checkbox "Use the same model for everything" is only a frontend convenience that writes the same config into all three lanes. Config is managed via `GET/PUT /v1/llm/config`; `/status` returns one entry per lane.

Providers all implement `chat()` + `embed()` + `ping()`. OpenAI-compatible providers (LM Studio, OpenAI, OpenRouter, Gemini) use one [`OpenAICompatibleProvider`](apps/api/app/services/llm/openai_compatible.py) driven by [`presets.py`](apps/api/app/services/llm/presets.py). Anthropic is the only native transport in [`anthropic_provider.py`](apps/api/app/services/llm/anthropic_provider.py). To add another OpenAI-compatible provider, add one preset, update the `ProviderName` Literal in `schemas.py`, and update frontend `PROVIDER_DEFAULTS`/`PROVIDER_LABELS`/`EMBED_INCAPABLE` in `ProviderForm.tsx`. **Hard-won quirks** baked in — don't undo:
- LM Studio rejects `response_format: json_object` (HTTP 400) → we never send it; for JSON mode we prepend a system hint.
- Reasoning models (Qwen3, DeepSeek-R1) emit `<think>...</think>` blocks → stripped in `_clean_response()`. If `content` is empty, fall back to `reasoning_content`.
- `max_tokens=None` → `lmstudio` passes `-1` (no cap, uses full context window); Anthropic requires it, so we default to 16000.
- `llm_service.parse_json()` repairs truncated JSON by closing unclosed brackets/quotes — necessary because thinking models often run out of budget mid-object.

### Flow Writing pipeline (the heart of the app)
[`services/flow_service.py`](apps/api/app/services/flow_service.py) implements the three-step writer loop from Story Forge:

1. `polish(raw, notes)` → polished prose using `POLISH_SYSTEM` + full story context from `build_story_context`
2. `extract(polished)` → structured JSON with characters, relationships, locations, factions, themes, events, threads + title/summary/POV suggestions. Existing entities are matched by name and flagged `is_new=false`.
3. `approve(payload)` → commits everything atomically:
   - creates/overwrites the chapter (supports `target_chapter_id` for redo + `target_chapter_number` for gap fill)
   - adds new characters/locations/factions/themes/events with name-based dedup
   - adds new relationships between extracted characters
   - **updates** existing plot threads (status evolution open→paid_off, description append)
   - links chapter to relevant plot threads
   - snapshots full story state into `story_versions`
   - fires `graph_service.reproject_story()` (best-effort, swallows errors)
   - marks all open `flow_drafts` rows for the story as approved (prevents stale draft restoring on next visit)

The frontend autosaves the in-progress draft to `flow_drafts` ~900ms after typing stops; restores from the latest unapproved row on mount.

### Three graph layers
1. **Front-end Story Map** ([`components/graph/StoryMap.tsx`](apps/web/components/graph/StoryMap.tsx)) — `react-force-graph-2d`. Colors read CSS vars at runtime so it adapts to light/dark.
2. **Neo4j knowledge graph** — [`services/graph_service.py::reproject_story()`](apps/api/app/services/graph_service.py) wipes the per-story subgraph (`MATCH (n {story_id: $s}) DETACH DELETE n`) and rebuilds from Postgres. Whitelist of node labels and edge types defined in `RELATIONSHIP_TYPE_MAP`. If Neo4j unreachable, falls back to a Postgres-derived view (graph still works in UI, just stays in-memory).
3. **Graph-RAG** ([`services/rag_service.py`](apps/api/app/services/rag_service.py)) — combines Qdrant vector hits (chunks embedded by [`embedding_service.py`](apps/api/app/services/embedding_service.py)) with Neo4j 1-hop character subgraphs. Returned as a Markdown block injected into LLM context via `build_story_context(extra_graph_block=...)`. Used by Flow polish/extract, Writing Companion, Story Check. Each layer fails independently — vector down → graph still works, both down → returns empty (callers handle gracefully).

### Auth & request scoping
JWT (HS256, 8h access + 7d refresh) via [`core/security.py`](apps/api/app/core/security.py). `get_current_user` dep in [`core/deps.py`](apps/api/app/core/deps.py); every story route uses `get_user_story(story_id, user, db)` which filters by `user_id` and raises `NotFound` (not Forbidden) for missing/foreign stories — intentional to not leak existence. Per-user LLM API keys encrypted at rest with Fernet (`LLM_KEY_ENCRYPTION_KEY` env).

### Config gotcha
[`core/config.py`](apps/api/app/core/config.py) resolves `.env` to an **absolute path** anchored at `apps/api/.env` — required because uvicorn often launches from a different cwd and the default relative `.env` would silently fall back to the default SQLite, creating an empty stray DB. Don't change this back to relative.

### Frontend conventions

**Color palette** lives as CSS variables in [`globals.css`](apps/web/app/globals.css) (`:root` light, `.dark` dark). Tailwind colors `ink-bg`, `ink-gold`, etc. resolve to `rgb(var(--ink-*) / <alpha>)`. So `bg-ink-gold/10`, `text-ink-text2` work in both themes — write components once. **Don't** use raw Tailwind tints like `text-red-200`; use `text-ink-red`. Theme persistence + no-flash hydration via [`ThemeBoot.tsx`](apps/web/components/shell/ThemeBoot.tsx) (inline script in `<head>`) + [`ThemeToggle.tsx`](apps/web/components/shell/ThemeToggle.tsx).

**BusyOverlay** ([`components/shell/BusyOverlay.tsx`](apps/web/components/shell/BusyOverlay.tsx)) shows a full-viewport blocking spinner while any mutation tagged `mutationKey: ["llm", "<name>"]` is pending. Always tag AI mutations this way — `<name>` is matched against `LABELS`/`HINTS` maps in the overlay for the human-readable status.

**TanStack Query** config: `staleTime: 0`, `refetchOnMount: "always"` ([`Providers.tsx`](apps/web/components/shell/Providers.tsx)) — so deleting a chapter on one tab immediately reflects on Flow Writing's "next chapter" hint. Don't add staleTime; rely on `invalidateQueries` for explicit refresh after mutations.

**Two navigation modes** in [`studio/[storyId]/layout.tsx`](apps/web/app/studio/[storyId]/layout.tsx): "Flow view" (the 6 Story Forge tabs — Flow, Chapters, Characters, World, Map, Check) ↔ "Studio view" (the 6 production stages — Foundation, Characters, Plot, Write, Produce, Review). Both navigate to the same set of routes; the toggle is purely a sidebar grouping.

**Chapter numbering** — the backend uses `max(number) + 1` on create/approve and **does not** renumber on delete (gaps are deliberate). The Flow page detects gaps and offers them as fill-targets in the "Save as" selector (plus "redo existing chapter" overwrite, via `target_chapter_id`).

### Data model

Single `users` → many `stories` → one `worlds` (story bible) + many `characters` / `chapters` / `locations` / `factions` / `themes` / `events` / `plot_threads` / `scene_cards` / `chapter_scripts` / `character_relationships`. Plus `flow_drafts` (autosaved in-progress Flow Writing), `story_versions` (immutable JSON snapshots — same shape as Story Forge backup format, round-trippable via `/v1/stories/import`), `continuity_reports` (Story Check history), `llm_runs` (LLM audit log), and `user_llm_settings` (per-user LLM router lanes JSON). Defined in [`db/models.py`](apps/api/app/db/models.py); Pydantic schemas in [`db/schemas.py`](apps/api/app/db/schemas.py).

`character_relationships` holds **one row per (source_id, target_id) pair** — Flow approve updates an existing pair's type/description in place rather than stacking duplicate rows (same evolve-don't-duplicate pattern as plot threads). Migrations live in [`apps/api/migrations/versions/`](apps/api/migrations/versions/) — currently `0001` (initial schema), `0002` (old split routing), and `0003` (simplified router lanes).

`chapters.character_ids` is a denormalized JSON list of character IDs present in the scene — kept in sync by Flow approve and used by the graph projection.

## Tests

Smoke tests at [`apps/api/tests/test_smoke.py`](apps/api/tests/test_smoke.py) cover the full signup → story → polish → extract → approve → graph view → export → story-check → user-isolation loop. They run against an unreachable LM Studio URL (`127.0.0.1:65535`) on purpose, forcing the fallback provider — so they exercise every degraded path without external services. Fixtures use in-memory SQLite and leave Neo4j/Qdrant unset.

When changing LLM behavior, run `pytest -v` against the unreachable LM Studio URL setup AND smoke-test with real LM Studio via the UI — the fallback path doesn't catch real-model issues (`response_format`, thinking models, JSON truncation).

## Common pitfalls hit during the build

- Stray empty `gink_dev.db` at project root means uvicorn ran from the wrong cwd and the env file resolution failed. Delete it, ensure `apps/api/.env` exists, and uvicorn must use the `apps/api/.venv/bin/uvicorn` binary.
- After editing Pydantic schemas, the running uvicorn won't always pick up changes even with `--reload` if it imported the stale class earlier. Hard restart with `pkill -f "uvicorn app.main"; ./run.sh`.
- `passlib` is incompatible with `bcrypt>=5` — we use the `bcrypt` lib directly via `core/security.py`. Don't reintroduce passlib.
- When adding a new entity type extracted from Flow, update **both** `FlowExtractResponse` (Pydantic schema) AND the matching insert/dedup loop in `flow_service.approve()`. Forgetting one means the field round-trips but never persists.
- When LM Studio's loaded model is a thinking model, polish output may still be empty even with our fixes if the model truly burns all tokens on reasoning. The frontend surfaces this via an alert prompting the user to switch model.
- After pulling changes that touch the schema, run `alembic upgrade head` (or just `./run.sh`, which does it). A "no such column: lanes" error at startup means migration `0003` hasn't been applied to your local `gink_dev.db`.
- Adding a provider that emits embeddings? Set `can_embed=True` in `presets.py` AND update `EMBED_INCAPABLE` (inverse) in `ProviderForm.tsx`; the frontend list is not auto-derived.
