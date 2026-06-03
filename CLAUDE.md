# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

G-Ink Novel Studio — a full-stack AI-powered writing studio. The product spec lives in [Story_Forge_Docs.md](Story_Forge_Docs.md) and the original single-file React reference is [story_forge.jsx](story_forge.jsx). Read them when in doubt about UX intent.

Monorepo with `apps/api` (FastAPI + SQLAlchemy 2 async + Alembic + ARQ) and `apps/web` (Next.js 15 App Router + React 19 + Tailwind + TanStack Query + Zustand). Optional Neo4j (graph) and Qdrant (vectors) for Graph-RAG; SQLite by default.

## Commands

| Task | Command |
|---|---|
| Run the whole stack locally | `./run.sh` (kills old uvicorn/next, runs migrations, streams `[api]`/`[web]` logs, Ctrl+C stops both) |
| First-time backend setup | `cd apps/api && python3 -m venv .venv && ./.venv/bin/pip install -e .[dev]` |
| First-time frontend setup | `cd apps/web && npm install --legacy-peer-deps` |
| Backend tests | `cd apps/api && .venv/bin/pytest -v` (~76 tests) |
| Single test | `.venv/bin/pytest tests/test_smoke.py::test_full_flow -v` |
| New migration | `cd apps/api && .venv/bin/alembic revision --autogenerate -m "msg"` |
| Apply migrations | `cd apps/api && .venv/bin/alembic upgrade head` (current head: **0015**) |
| Frontend lint | `cd apps/web && npm run lint` |
| Frontend build | `cd apps/web && npm run build` |
| Docker (full stack with Neo4j+Qdrant+Postgres) | `docker compose up -d` |
| Background worker | `REDIS_URL=redis://localhost:6379 .venv/bin/arq app.workers.export_worker.WorkerSettings` |

Always invoke backend tools via `apps/api/.venv/bin/<tool>` — the system Python's tools (uvicorn, alembic) shadow the venv if PATH ordering is bad (conda `(base)` is a common offender).

## Architecture

### Response envelope
**Every** API route returns `{"ok": bool, "data": any, "error": {code, message, details} | null}` via `envelope_ok(...)` / `envelope_err(...)` in [`core/errors.py`](apps/api/app/core/errors.py). The frontend's `request<T>()` in [`lib/api.ts`](apps/web/lib/api.ts) unwraps `data` and throws `ApiError` on `ok: false`. Don't return bare dicts from routes.

### LLM provider abstraction
**Every** AI call must go through `llm_service.run(db, user, page=..., system=..., user_msg=..., ...)` in [`services/llm_service.py`](apps/api/app/services/llm_service.py). Never call a provider directly from a router. The service:
- resolves the provider via `get_provider_for_page(db, user, page)` in [`services/llm/factory.py`](apps/api/app/services/llm/factory.py) — the `page` string is the routing key
- logs every call to `llm_runs` with timing/tokens/excerpts (and the resolved provider — your audit trail for which model handled which task)
- on failure, retries on the deterministic [`FallbackProvider`](apps/api/app/services/llm/fallback.py) so the UI never breaks
- treats a **blank/empty** HTTP-200 response (a reasoning model that burned its budget on `<think>`, truncated, or refused) the same as a raised error → routes through the fallback, returns `fallback=True`, and downgrades the run to `key_source="none"` so an empty answer is never metered. Don't "fix" this by removing the empty check — silent empty results that still bill tokens were a real bug. `parse_json()` uses `raw_decode` so valid JSON followed by trailing prose still parses.

**Routing (simple lanes).** A user has one `user_llm_settings.lanes` JSON object with three slots: `creative`, `technical`, and `embedding`. [`services/llm/roles.py`](apps/api/app/services/llm/roles.py) maps each `page` to a category: `flow.polish`/`flow.companion`/`story_check` → **creative**, `flow.extract`/`llm.test` → **technical**, unknown → technical. `get_provider_for_page` reads the lane for that category. The Settings checkbox "Use the same model for everything" is only a frontend convenience that writes the same config into all three lanes. Config is managed via `GET/PUT /v1/llm/config`; `/status` returns one entry per lane.

**Embeddings go through `llm_service.embed(db, user, texts, story_id=...)`** — the single choke point (used by `rag_service` query embeds AND `embedding_service.index_story`). It resolves `get_embedding_provider_with_source` → `(provider, key_source)`: BYOK/owner use the user's **embedding lane** (`key_source="user"`, they pay their own provider); house tiers (free/dev_ai) use the **house embedder** (`key_source="server"`). A non-embed-capable lane or missing BYOK key degrades to local LM Studio (`key_source="none"`). Only `"server"` embeddings are **metered** — logged to `llm_runs` (page `"embedding"`) via a *fresh committed session* (so the SSE companion stream, which never commits the request session, still records it) so house embedding cost counts against the plan instead of being an invisible leak. Don't call `provider.embed()` directly on a cost-bearing path — route it through `llm_service.embed`.

Providers all implement `chat()` + `embed()` + `ping()`. OpenAI-compatible providers (LM Studio, OpenAI, OpenRouter, Gemini) use one [`OpenAICompatibleProvider`](apps/api/app/services/llm/openai_compatible.py) driven by [`presets.py`](apps/api/app/services/llm/presets.py). Anthropic is the only native transport in [`anthropic_provider.py`](apps/api/app/services/llm/anthropic_provider.py). To add another OpenAI-compatible provider, add one preset, update the `ProviderName` Literal in `schemas.py`, and update frontend `PROVIDER_DEFAULTS`/`PROVIDER_LABELS`/`EMBED_INCAPABLE` in `ProviderForm.tsx`. **Hard-won quirks** baked in — don't undo:
- LM Studio rejects `response_format: json_object` (HTTP 400) → we never send it; for JSON mode we prepend a system hint.
- Reasoning models (Qwen3, DeepSeek-R1) emit `<think>...</think>` blocks → stripped in `_clean_response()`. If `content` is empty, fall back to `reasoning_content`.
- `max_tokens=None` → `lmstudio` passes `-1` (no cap, uses full context window); Anthropic requires it, so we default to 16000.
- `llm_service.parse_json()` repairs truncated JSON by closing unclosed brackets/quotes — necessary because thinking models often run out of budget mid-object.

### Prompt safety (injection hardening)
Any LLM call that injects author-controlled text **must** use [`core/prompt_safety.py`](apps/api/app/core/prompt_safety.py):

```python
from app.core.prompt_safety import SECURITY_CLAUSE, fence

user_msg = f"STORY CONTEXT:\n{fence('story_context', ctx)}\n\nDRAFT:\n{fence('author_draft', raw)}"
system = MY_SYSTEM + "\n\n" + SECURITY_CLAUSE
```

`fence(tag, content)` wraps untrusted content in `<tag>…</tag>` and defangs any fence tag (open or close, any case/whitespace variant) appearing inside via a regex that covers all six known tag names (`story_context`, `author_draft`, `polished_scene`, `revision_notes`, `author_text`, `author_instruction`). `SECURITY_CLAUSE` tells the model that everything inside tags is story material, never an instruction. All Flow pipeline calls (polish, extract, enhance, companion) are already wired — extend the pattern for any new prompt that touches author text.

### Flow Writing pipeline (the heart of the app)
[`services/flow_service.py`](apps/api/app/services/flow_service.py) implements the three-step writer loop from Story Forge:

1. `polish(raw, notes)` → polished prose using `POLISH_SYSTEM` + full story context + `SECURITY_CLAUSE`. Author draft wrapped in `fence('author_draft', raw)`. Optional **scene setup** (`scene_character_ids`/`scene_location_id`, set via the "Scene setup" picker under the Flow free-write box) pins those characters' FULL Voice Studio identity (+ masks + active state) and the location's place identity in a `# SCENE FOCUS` section (priority `_P_SCENE_FOCUS=94`, never trimmed) — so in-scene characters always get their complete voice even on huge manuscripts. Blank → unchanged.
2. `extract(polished)` → structured JSON. Context built with `include_entity_ids=True` so each CAST entry shows its stable `[id:…]`; the model echoes the id back in `character_id` to unambiguously identify existing cast members.
3. `approve(payload)` → commits everything atomically:
   - creates/overwrites the chapter (supports `target_chapter_id` for redo + `target_chapter_number` for gap fill)
   - adds new characters/locations/factions/themes/events with name-based dedup
   - adds new relationships between extracted characters
   - **updates** existing plot threads (status evolution open→paid_off, description append)
   - links chapter to relevant plot threads
   - snapshots full story state into `story_versions`
   - fires `graph_service.reproject_story()` (best-effort, swallows errors) + commits graph status
   - marks all open `flow_drafts` rows for the story as approved

**Character disambiguation in approve():** a `name_to_any_id` map is built that deliberately omits ambiguous names (same name, multiple cast members) unless the extract echoed a valid `existing_id` for them. ALL downstream identity resolution — chapter.character_ids, POV, event involvement, relationships, scene members, revelation knowers — routes through `name_to_any_id` or `_resolve_ids_from_names(names, name_to_any_id)`. An ambiguous name without an id resolves to nothing, never to the wrong record.

The frontend autosaves the in-progress draft to `flow_drafts` ~900ms after typing stops; restores from the latest unapproved row on mount.

### Character Voice Studio (Narrative Fidelity Engine)
A layer ABOVE the Story Engine: the Story Engine tracks *what is true* (canon, plot, timeline); this module tracks *how the story feels on the page* (voice, behavior, atmosphere, prose fidelity). Frontend tab at [`studio/[storyId]/voice`](apps/web/app/studio/[storyId]/voice/page.tsx) (route `/voice`); the Characters tab is now a read-only roster (name/role/status/age/icon) that links into Voice Studio for the depth — **one source of truth**.

**Backend API namespace:** `/{story_id}/identity/*`, `/{story_id}/observer/*`, `/{story_id}/place/*` — deliberately NOT `/{story_id}/voice/*`, which is the existing deterministic profile endpoints in [`narrative.py`](apps/api/app/api/v1/narrative.py). Routers: [`api/v1/identity.py`](apps/api/app/api/v1/identity.py) + [`api/v1/observer.py`](apps/api/app/api/v1/observer.py). Services: [`identity_service.py`](apps/api/app/services/identity_service.py) (the 5 layers + 2 build methods) + [`observer_service.py`](apps/api/app/services/observer_service.py) (Observer/rewrite/place/evolve/compare). Static question banks in [`identity_questions.py`](apps/api/app/services/identity_questions.py) (pure data → unit-testable without LLM, branch-aware).

**5-layer identity** (migration 0013): `character_identities` holds layers 1-3 as JSON columns (`core_personality`, `behavioral_patterns`, `voice_fingerprint` — QUALITATIVE only); `relationship_masks` is layer 4 (per-audience speech style — distinct from `character_relationships`, which is a bond type); `character_states` is layer 5 (scene-scoped, `kind` = temporary|recurring|arc); `identity_versions` is append-only history + arc timeline (snapshots the *changed layer only*, pruned to 50 per (character, kind)); `place_identities` is the rich 1:1 companion to `Location`; `voice_exceptions` persists "mark intentional".

**Legacy projection (back-compat, do NOT remove):** the legacy free-text `Character` columns (`personality`/`backstory`/`motivation`/`flaw`/`arc`) stay the **context-read source**. `identity_service.compile_to_legacy()` recompiles them from the structured layers on every save, so `build_story_context`'s CAST section keeps working unchanged and gets richer content for free. The structured layers are authoritative; legacy columns are a derived view. `seed_from_existing()` does the reverse (legacy → seed layer) lazily on first open.

**The deterministic voice stats** (`CharacterVoiceProfile`, from [`voice_service.py`](apps/api/app/services/voice_service.py)) are the QUANTITATIVE half of the Voice Fingerprint and are NOT duplicated — `context_builder` emits them in `# CHARACTER VOICE FINGERPRINTS` while the qualitative descriptors go in the new `# CHARACTER IDENTITY` section.

**ONE identity vocabulary = the interview question ids.** This is load-bearing: the `core_personality`/`behavioral_patterns`/`voice_fingerprint` JSON layers are keyed by the **interview question ids** ([`identity_questions.py`](apps/api/app/services/identity_questions.py): core = `want,need,lie,wound,shame,value_hierarchy,moral_line,self_gap`; behavioral = `stress_response,vulnerability,criticism,deception,decision_tempo,anger_tell,recovery`; voice = `cadence,directness,lexicon,emotion_shift,register,silence,humor` + nested `shifts`). EVERY producer and consumer uses these same keys: analyze/approve store by `question_id`; `INTERVIEW_SYNTH_SYSTEM` emits these keys; the frontend editor field set ([`voice/_components/layers.ts`](apps/web/app/studio/[storyId]/voice/_components/layers.ts)) uses them as `key`; `context_builder` `_CTX_*_KEYS` reference them; `compile_to_legacy`/`seed_from_existing` map a subset to the legacy `personality`/`motivation`/`flaw` columns. **If you add/rename a layer field, change it in ALL of those places or stored data goes invisible in the editor** (an earlier split — editor used `worldview/values/sentence_length…` while analyze stored `want/lie/cadence…` — meant only `worldview`+`directness` overlapped and everything else vanished from the UI; migration `migrate_vocab` remapped existing rows, and the IdentityPanel now also renders any unrecognized stored key as a safety net).

**Interview & analyze.** Tiers: Quick 10 / Medium 20 / Deep 35, all 5 layers. The interview tags answers by layer for synthesis (relationship→`RelationshipMask` rows, current→`CharacterState` rows). **Analyze-existing-writing is anchored to the actual bank questions** — `analyze_writing` injects `extractable_questions()` (core/behavioral/voice only; masks/state are interview-driven) and the model answers each by `question_id`. Models often echo the id as `"lie [core]"`, so the parser strips any trailing `[...]`/`(...)` before lookup. Analyze accepts selected chapter ids and/or pasted text, packed under `ANALYZE_SAMPLE_BUDGET = 128_000` chars (whole chapters in number order; overflow truncated with a marker; returns `used_chapters`/`truncated`); the UI warns past ~60k that it's a heavy, plan-metered call. The IdentityPanel re-syncs the editor `draft` from the server on `updated_at` change (not just character switch), so approved traits appear immediately.

**LM Studio model resolution:** when the configured model is a placeholder (`local-model`/empty/`auto`), `OpenAICompatibleProvider._resolve_model` queries `/models` and uses the loaded one (cached). This prevents a 400 ("Invalid model identifier 'local-model'" / "Multiple models loaded, specify a model") from silently dropping every AI call to the deterministic fallback.

**Context integration:** new droppable sections `# CHARACTER IDENTITY`, `# RELATIONSHIP MASKS`, `# PLACE IDENTITY` at priorities `_P_IDENTITY=30`/`_P_MASKS=36`/`_P_PLACE=34` — all below `_ALWAYS_KEEP=90`, so rich identity degrades by *detail* first; the cast roster is never dropped. `CONTEXT_CHAR_BUDGET` is unchanged. So the identity flows into polish / Writing Companion / Story Check automatically.

**Narrative Observer** (`observer_service.observe`): line-level critique evolving the Story Check dialogue pass. Each note quotes an exact draft line; the analyzed draft goes in the **request body** (`fence('author_draft', …)`), not context. "Mark intentional" stores a `line_fingerprint(character_id, normalized_line, note_kind)` in `voice_exceptions`; the next critique filters out any candidate note whose fingerprint matches — so a deliberate deviation stops re-flagging (a real rewrite of the line changes its fingerprint and surfaces again). Strictness slider also sets a min-confidence cutoff. **Post-scene evolve** proposes identity deltas with a temporary/recurring/permanent/not_saved save-as gate so one-offs don't pollute the profile.

**LLM page keys** (in [`roles.py`](apps/api/app/services/llm/roles.py)): `voice.analyze`/`voice.evolve` → technical (JSON), `voice.interview`/`voice.place`/`voice.observe`/`voice.rewrite`/`voice.compare` → creative. Every AI surface tolerates the fallback provider returning non-JSON (`parse_json(...) or {}` + `isinstance` guards) and preserves the author's raw input when the model returns junk. New fenced spans reuse the registered `author_draft`/`author_text`/`author_instruction` tags — no `prompt_safety.py` change needed. Frontend AI mutations tagged `mutationKey: ["llm", "voice.*"]` with labels in `BusyOverlay.tsx`.

### Three graph layers
1. **Front-end Story Map** ([`components/graph/StoryMap.tsx`](apps/web/components/graph/StoryMap.tsx)) — `react-force-graph-2d`. Colors read CSS vars at runtime so it adapts to light/dark.
2. **Neo4j knowledge graph** — [`services/graph_service.py::reproject_story()`](apps/api/app/services/graph_service.py) wipes the per-story subgraph (`MATCH (n {story_id: $s}) DETACH DELETE n`) and rebuilds from Postgres. Whitelist of node labels and edge types defined in `RELATIONSHIP_TYPE_MAP`. If Neo4j unreachable, falls back to a Postgres-derived view. `stories.graph_synced_at` is stamped on success; `reconcile_stale_graphs()` retried by the ARQ cron.
3. **Graph-RAG** ([`services/rag_service.py`](apps/api/app/services/rag_service.py)) — combines Qdrant vector hits (chunks embedded by [`embedding_service.py`](apps/api/app/services/embedding_service.py)) with Neo4j 1-hop character subgraphs. Returned as a Markdown block injected into LLM context via `build_story_context(extra_graph_block=...)`. Used by Flow polish/extract, Writing Companion, Story Check. Each layer fails independently — vector down → graph still works, both down → returns empty (callers handle gracefully).

### Qdrant / embedding layout
All stories share **one collection** `gink_chunks`, partitioned by a `story_id` payload field (keyword index). This is the standard multi-tenant vector pattern. Old per-story `story_{id}_chunks` collections (pre-0012 layout) are migrated and dropped automatically on the next reindex. Point IDs are deterministic UUID5s keyed on `(story_id, kind, ref_id, chunk_idx)` so re-indexing upserts in place without duplicating.

`_chunk_text()` packs on paragraph → sentence boundaries (ASCII `.!?` + CJK `。！？` + Arabic `؟`), never cuts mid-sentence. Each `SceneCard` is embedded as one whole point via `_scene_text()` — a scene is always retrieved complete, never sliced.

`search()` falls back to the legacy per-story collection when the shared collection has no hits for a story yet (zero-downtime migration window), but only when the shared collection's query succeeded and returned zero — not on a transient error.

### Auth & request scoping
**Clerk** (JWKS/OIDC) is the default auth in staging/prod, configured via `CLERK_JWKS_URL` + `CLERK_ISSUER` env vars. `get_current_user` in [`core/deps.py`](apps/api/app/core/deps.py) verifies the Bearer token against the JWKS endpoint. On first request from a Clerk user, `resolve_user()` in `clerk_service.py` creates a local `users` row (lazy provisioning — no webhook required for dev).

**Legacy password auth** (JWT HS256, `core/security.py`) is available when `LEGACY_PASSWORD_AUTH=1` is set — used by the test suite and local dev without a Clerk account. The two paths share the same `get_current_user` dep; it tries Clerk first, falls back to HS256.

Every story route uses `get_user_story(story_id, user, db)` which filters by `user_id` and raises `NotFound` (not Forbidden) for missing/foreign stories — intentional to not leak existence. Per-user LLM API keys encrypted at rest with Fernet (`LLM_KEY_ENCRYPTION_KEY` env).

`clerk_service.resolve_user` adopts a pre-existing local account by matching email — but for **sensitive accounts** (admin or active-paid, see `_is_sensitive_account`) it first requires Clerk to report the email as *verified*, or it refuses the sign-in (closes an email-spoof takeover). **Force-logout** is `POST /v1/admin/users/{id}/logout`: it bumps `users.token_version` (instantly invalidates legacy HS256 tokens) AND calls `clerk_service.revoke_user_sessions` (Clerk Backend API) to kill active Clerk sessions. BYOK `base_url`s are SSRF-checked at write time (`validate_provider_base_url`) and re-checked before every outbound call (`_guard_url` in the OpenAI-compatible provider); set `ALLOWED_LLM_HOSTS` to flip on an opt-in strict host allowlist (default off allows any public host for self-hosted proxies).

### Idempotency
`POST /flow/approve` and `POST /publish/{id}/push` accept an `Idempotency-Key` header. [`core/idempotency.py`](apps/api/app/core/idempotency.py) stores `(user_id, scope, key) → response` in the `idempotency_keys` table. `replay()` short-circuits before running work; `remember()` stores after commit. Without the header, behavior is unchanged. Scopes: `flow.approve:{story_id}`, `publish.push:{pub_id}`.

### Context builder
[`services/context_builder.py`](apps/api/app/services/context_builder.py) assembles sections as `(priority, lines)` tuples packed under `CONTEXT_CHAR_BUDGET = 28_000` chars (~7k tokens). Sections at or above `_ALWAYS_KEEP = 90` (world bible, full cast, graph slice) are never dropped. Lower-priority sections (scenes, revelations, voice fingerprints) are dropped first when over budget. Under-budget stories produce byte-identical output to a naive join.

`build_story_context(..., include_entity_ids=True)` appends `[id:…]` to each CAST entry — used only for the extract call so the model can echo ids back for character disambiguation. Prose calls (polish, companion) use the default `include_entity_ids=False`.

### Background worker (ARQ)
[`workers/export_worker.py`](apps/api/app/workers/export_worker.py) — started separately with `arq app.workers.export_worker.WorkerSettings` (needs `REDIS_URL`). Handles:
- `export_pdf_task` / `export_epub_task` — async export, result cached in Redis for 5 min
- `reconcile_graphs_task` (cron, every 5 min) — calls `graph_service.reconcile_stale_graphs(limit=50)` to repair stories whose Neo4j projection drifted (Neo4j was down during approve, process died, etc.)

Without the worker running, export falls back to synchronous, and the graph reconciler simply doesn't fire.

### Config gotcha
[`core/config.py`](apps/api/app/core/config.py) resolves `.env` to an **absolute path** anchored at `apps/api/.env` — required because uvicorn often launches from a different cwd and the default relative `.env` would silently fall back to the default SQLite, creating an empty stray DB. Don't change this back to relative.

### Frontend conventions

**Color palette** lives as CSS variables in [`globals.css`](apps/web/app/globals.css) (`:root` light, `.dark` dark). Tailwind colors `ink-bg`, `ink-gold`, etc. resolve to `rgb(var(--ink-*) / <alpha>)`. So `bg-ink-gold/10`, `text-ink-text2` work in both themes — write components once. **Don't** use raw Tailwind tints like `text-red-200`; use `text-ink-red`. Theme persistence + no-flash hydration via [`ThemeBoot.tsx`](apps/web/components/shell/ThemeBoot.tsx) (inline script in `<head>`) + [`ThemeToggle.tsx`](apps/web/components/shell/ThemeToggle.tsx).

**BusyOverlay** ([`components/shell/BusyOverlay.tsx`](apps/web/components/shell/BusyOverlay.tsx)) shows a full-viewport blocking spinner while any mutation tagged `mutationKey: ["llm", "<name>"]` is pending. Always tag AI mutations this way — `<name>` is matched against `LABELS`/`HINTS` maps in the overlay for the human-readable status.

**TanStack Query** config: `staleTime: 0`, `refetchOnMount: "always"` ([`Providers.tsx`](apps/web/components/shell/Providers.tsx)) — so deleting a chapter on one tab immediately reflects on Flow Writing's "next chapter" hint. Don't add staleTime; rely on `invalidateQueries` for explicit refresh after mutations.

**Two navigation modes** in [`studio/[storyId]/layout.tsx`](apps/web/app/studio/[storyId]/layout.tsx): "Flow view" (the 6 Story Forge tabs — Flow, Chapters, Characters, World, Map, Check) ↔ "Studio view" (the 6 production stages — Foundation, Characters, Plot, Write, Produce, Review). Both navigate to the same set of routes; the toggle is purely a sidebar grouping.

**Chapter numbering** — the backend uses `max(number) + 1` on create/approve and **does not** renumber on delete (gaps are deliberate). The Flow page detects gaps and offers them as fill-targets in the "Save as" selector (plus "redo existing chapter" overwrite, via `target_chapter_id`).

### Data model

Single `users` → many `stories` → one `worlds` (story bible) + many `characters` / `chapters` / `locations` / `factions` / `themes` / `events` / `plot_threads` / `scene_cards` / `chapter_scripts` / `character_relationships`. Plus:
- `flow_drafts` — autosaved in-progress Flow Writing (restored on mount)
- `story_versions` — immutable JSON snapshots (round-trippable via `/v1/stories/import`)
- `continuity_reports` — Story Check history
- `llm_runs` — LLM audit log (provider, model, page, timing, tokens)
- `user_llm_settings` — per-user LLM router lanes JSON
- `idempotency_keys` — dedup table `(user_id, scope, idem_key)` → response JSON
- Publishing: `publications`, `pub_chapters`, `pub_subscriptions`, `reader_comments`, etc.

`character_relationships` holds **one row per (story_id, source_id, target_id)** — DB-enforced by `uq_character_relationship_pair`; both Flow `approve` and the manual POST route upsert (update-in-place) so re-adding an edge never trips it. `chapters.character_ids` is a denormalized JSON list kept in sync by approve and used by the graph projection.

### Concurrency & conflict handling
`Chapter`, `SceneCard`, and `Character` carry a `version_id` column wired as SQLAlchemy `version_id_col` (`__mapper_args__`). Every ORM UPDATE adds `WHERE version_id=:old` and bumps it, so a concurrent read-modify-write (two tabs autosaving the same chapter) loses → `StaleDataError`. **Global exception handlers in [`main.py`](apps/api/app/main.py)** convert `StaleDataError` → **409** and any `IntegrityError` (check-then-act unique collisions) → **409** with the real error logged; the web `MutationCache.onError` shows a non-destructive alert on 409 (it does NOT auto-refetch, to avoid wiping in-progress edits). This is intra-request optimistic locking (no client-supplied `If-Match`); it catches simultaneous writes, not a stale client that read minutes ago. SQLite enforces FKs via a `PRAGMA foreign_keys=ON` connect listener in [`session.py`](apps/api/app/db/session.py) so the test suite catches cascade regressions (prod Postgres always enforces them).

Migrations live in [`apps/api/migrations/versions/`](apps/api/migrations/versions/) — current head **0015** (optimistic-locking `version_id` columns + `character_relationships` unique pair). 0014 = site settings + owner "act as"; the Character Voice Studio tables (`character_identities`, `relationship_masks`, `character_states`, `place_identities`, `voice_exceptions`, `identity_versions`) were added in **0013**. [`test_migration_drift.py`](apps/api/tests/test_migration_drift.py) fails CI if a model table/column has no migration — but it intentionally **ignores** nullability/server_default/index (too noisy across SQLite↔Postgres), so those won't be caught.

## Tests

76 tests across several files:
- `test_smoke.py` — full signup → story → polish → extract → approve → graph view → export → story-check → user-isolation loop
- `test_audit_fixes.py` — context budget packing (C1), pagination (H6), idempotency (H8)
- `test_audit_fixes_p2.py` — prompt injection fences (M5), character disambiguation (H3), scene-boundary chunking (M2), single Qdrant collection (M7)
- `test_voice_studio.py` — Voice Studio: identity CRUD + legacy projection, masks/states, context integration + degrade-by-detail, scene-focus pinning (SCENE FOCUS survives a tiny budget, no duplication), interview bank/synth, analyze+approve, place build, observer mark-intentional re-filter, rewrite/evolve/compare, fingerprint normalization
- `test_migration_drift.py` — confirms Alembic head matches SQLAlchemy models (auto-validates new migrations)
- `test_deferred_features.py`, `test_subscriptions.py`, `test_llm_routing.py` — feature and provider routing coverage

All tests run against an unreachable LM Studio URL (`127.0.0.1:65535`), forcing the fallback provider — every degraded path without external services. Neo4j/Qdrant left unset; Clerk auth disabled via `LEGACY_PASSWORD_AUTH=1`.

When changing LLM behavior, run `pytest -v` AND smoke-test with real LM Studio via the UI — the fallback path doesn't catch real-model issues (`response_format`, thinking models, JSON truncation).

## Common pitfalls

- Stray empty `gink_dev.db` at project root means uvicorn ran from the wrong cwd. Delete it, ensure `apps/api/.env` exists, use `apps/api/.venv/bin/uvicorn`.
- After editing Pydantic schemas, hard restart uvicorn — `pkill -f "uvicorn app.main"; ./run.sh`.
- `passlib` is incompatible with `bcrypt>=5` — we use `bcrypt` directly. Don't reintroduce passlib.
- When adding a new entity type to Flow extract, update **both** `FlowExtractResponse` (Pydantic) AND the insert/dedup loop in `flow_service.approve()`. Forgetting one means the field round-trips but never persists.
- When LM Studio's loaded model is a thinking model, polish may still return empty if the model burns all tokens on `<think>`. The frontend surfaces an alert prompting a model switch.
- After pulling schema changes, run `alembic upgrade head` (or `./run.sh`). "no such column" at startup = unapplied migration.
- Adding a provider that emits embeddings? Set `can_embed=True` in `presets.py` AND update `EMBED_INCAPABLE` in `ProviderForm.tsx` — the list is not auto-derived.
- `expire_on_commit=False` is set on the session factory (`session.py`) — don't remove it. The post-approve graph commit reads `chapter.id` after the main commit; a rollback in the graph except path would force-expire it.
- The CAST in the extract context includes `[id:…]` per character. Never surface these to prose prompts (polish/companion) — they add noise without benefit. `include_entity_ids=True` is extract-only.
