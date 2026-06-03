# Contributing

Thanks for being interested in G-Ink Novel Studio.

## Setup

`./run.sh` (see [RUN.md](RUN.md) for the longer story).

## Architecture orientation

Start with [CLAUDE.md](CLAUDE.md) — it covers the response envelope, the LLM provider contract, the Flow Writing pipeline, auth, and the three graph layers. Then read [Story_Forge_Docs.md](Story_Forge_Docs.md) for the product intent.

## Before opening a PR

- `cd apps/api && .venv/bin/pytest -v` — all tests pass (~73 currently).
- `cd apps/web && npm run lint && npm run build` — frontend compiles.
- If you touched the DB schema, generate a migration: `.venv/bin/alembic revision --autogenerate -m "what changed"`. Current head: **0013**. (`test_migration_drift.py` will fail if a model has no matching migration.)
- If you added a new AI call, route it through `llm_service.run(...)` and tag the front-end mutation with `mutationKey: ["llm", "<name>"]` so the BusyOverlay picks it up.
- If your call injects author-controlled text into a prompt, wrap it with `fence(tag, content)` from `app.core.prompt_safety` and append `SECURITY_CLAUSE` to the system prompt.
- If you're resolving a character name to an id (approve flow or similar), use `name_to_any_id` (which excludes ambiguous names) rather than `existing_by_name` directly.

## Code style

- Backend: ruff defaults (configured in `apps/api/pyproject.toml`).
- Frontend: `next lint`.
- No comments that just restate the code. A comment should explain *why*, not *what*.

## Security rules (carry these forward)

- Secrets (`CLERK_SECRET_KEY`, `CLERK_WEBHOOK_SECRET`, `JWT_SECRET`, `LLM_KEY_ENCRYPTION_KEY`) must **never** appear in any git-tracked file.
- `run.sh` (git-tracked) may only contain public Clerk identifiers (JWKS URL, issuer, publishable key `pk_test`). Real secrets go in gitignored `apps/api/.env` and `apps/web/.env.local`.
- `ADMIN_EMAILS` defaults to empty — must be set via env var; never hardcode an email.
- Any new endpoint that handles user-uploaded or author-written text must fence it with `prompt_safety.fence()` before sending to the LLM.

## What to avoid

The codebase has a handful of hard-won quirks documented in [CLAUDE.md](CLAUDE.md#llm-provider-abstraction) — read those before changing LLM providers, JSON parsing, or the `.env` config resolution.

Key ones:
- LM Studio rejects `response_format: json_object` — never send it; prepend a system hint instead.
- Thinking models (Qwen3, DeepSeek-R1) emit `<think>…</think>` — stripped in `_clean_response()`.
- `passlib` is incompatible with `bcrypt>=5` — don't reintroduce it.
- `expire_on_commit=False` is set on the session factory — don't remove it; the post-approve graph commit relies on it.
