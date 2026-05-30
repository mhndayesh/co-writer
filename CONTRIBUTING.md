# Contributing

Thanks for being interested in G-Ink Novel Studio.

## Setup

`./run.sh` (see [RUN.md](RUN.md) for the longer story).

## Architecture orientation

Start with [CLAUDE.md](CLAUDE.md) — it covers the response envelope, the LLM provider contract, the Flow Writing pipeline, and the three graph layers. Then read [Story_Forge_Docs.md](Story_Forge_Docs.md) for the product intent.

## Before opening a PR

- `cd apps/api && .venv/bin/pytest -v` — smoke tests pass.
- `cd apps/web && npm run lint && npm run build` — frontend compiles.
- If you touched the schema, generate a migration: `.venv/bin/alembic revision --autogenerate -m "what changed"`.
- If you added a new AI call, route it through `llm_service.run(...)` and tag the front-end mutation with `mutationKey: ["llm", "<name>"]` so the BusyOverlay picks it up.

## Code style

- Backend: ruff defaults (configured in `apps/api/pyproject.toml`).
- Frontend: `next lint`.
- No comments that just restate the code. A comment should explain *why*, not *what*.

## What to avoid

The codebase has a handful of hard-won quirks documented in [CLAUDE.md](CLAUDE.md#llm-provider-abstraction) — read those before changing the LLM providers, JSON parsing, or the `.env` config resolution.
