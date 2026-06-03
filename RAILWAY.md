# Deploy G-Ink Co-Writer on Railway (full stack)

Railway deploys straight from this GitHub repo — no CLI needed. You create one
**project** containing **7 services**, all pointing at `github.com/mhndayesh/co-writer`:

| Service | Source | Notes |
|---|---|---|
| **Postgres** | Railway database | one-click; gives `DATABASE_URL` |
| **Redis** | Railway database | one-click; gives `REDIS_URL` |
| **Neo4j** | Docker image `neo4j:5-community` | needs a Volume on `/data` |
| **Qdrant** | Docker image `qdrant/qdrant` | needs a Volume on `/qdrant/storage` |
| **api** | this repo, root `apps/api` | FastAPI; runs migrations on deploy |
| **worker** | this repo, root `apps/api` | arq background worker (cron + exports) |
| **web** | this repo, root `apps/web` | Next.js frontend; your custom domain attaches here |

> The repo is already wired for this: the API binds Railway's `$PORT`, the DB URL is
> auto-normalized to `asyncpg`, and `railway.json` files set the build + migrations +
> healthchecks. Neo4j + Qdrant are **optional power features** — if you skip them or
> they're unreachable, the app degrades gracefully (graph → Postgres view, vector
> search off). Leave `NEO4J_URI` / `QDRANT_URL` unset to disable.

---

## 0. Generate the two secrets (locally, once)

```bash
python3 -c "import secrets; print('JWT_SECRET=' + secrets.token_urlsafe(64))"
python3 -c "from cryptography.fernet import Fernet; print('LLM_KEY_ENCRYPTION_KEY=' + Fernet.generate_key().decode())"
```

## 1. Create the project + connect GitHub

Railway → **New Project** → **Deploy from GitHub repo** → pick `mhndayesh/co-writer`.
(Authorize Railway on the repo if asked.) This creates the first service from the repo —
you'll point it at `apps/api` in step 4.

## 2. Add the managed databases

In the project: **+ New → Database → Add PostgreSQL**, then again **→ Add Redis**.
Nothing to configure — they expose `DATABASE_URL` / `REDIS_URL`.

## 3. Add Neo4j + Qdrant (Docker-image services)

**+ New → Empty Service** (or "Docker Image") for each:
- **Neo4j** → image `neo4j:5-community`
  - Variables: `NEO4J_AUTH=neo4j/CHOOSE_A_PASSWORD`, `NEO4J_PLUGINS=["apoc"]`
  - **Storage → add a Volume** mounted at `/data`
- **Qdrant** → image `qdrant/qdrant`
  - **Storage → add a Volume** mounted at `/qdrant/storage`

> Railway's private network is IPv6. If the api logs show it can't reach these, set the
> server to listen on IPv6: Neo4j `NEO4J_server_default__listen__address=::`, Qdrant
> `QDRANT__SERVICE__HOST=::`. Not fatal — the app falls back if they're down.

## 4. Configure the **api** service

Select the service created in step 1 → **Settings**:
- **Root Directory:** `apps/api`  (so it builds `apps/api/Dockerfile` + reads `apps/api/railway.json`)
- **Networking → Generate Domain** → note it, e.g. `api-production-xxxx.up.railway.app`
  (or add a custom `api.yourdomain.com`)

**Variables** (paste — `${{...}}` are live references to the other services):

```
ENVIRONMENT=production
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}
NEO4J_URI=bolt://${{Neo4j.RAILWAY_PRIVATE_DOMAIN}}:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=THE_SAME_PASSWORD_YOU_SET_ON_NEO4J
QDRANT_URL=http://${{Qdrant.RAILWAY_PRIVATE_DOMAIN}}:6333

JWT_SECRET=...generated...
LLM_KEY_ENCRYPTION_KEY=...generated Fernet...

# Auth (Clerk production instance)
CLERK_JWKS_URL=https://clerk.yourdomain.com/.well-known/jwks.json
CLERK_ISSUER=https://clerk.yourdomain.com
CLERK_SECRET_KEY=sk_live_...
CLERK_WEBHOOK_SECRET=whsec_...

# CORS = the WEB public URL (set after step 6; can update later)
CORS_ORIGINS=https://yourdomain.com

# House AI (the key the site pays with for Free/Plus). DeepSeek example:
SYSTEM_LLM_PROVIDER=openai
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat
OPENAI_API_KEY=sk-...deepseek...

# Billing (Polar — Merchant of Record)
BILLING_PROVIDER=polar
POLAR_ACCESS_TOKEN=...
POLAR_WEBHOOK_SECRET=...
POLAR_SERVER=production
POLAR_PRODUCT_DEV_AI=...   # Plus  $19.99
POLAR_PRODUCT_BYOK=...     # BYOK  $4.99
BILLING_SUCCESS_URL=https://yourdomain.com/settings?billing=success
BILLING_CANCEL_URL=https://yourdomain.com/pricing?billing=cancel

# You = unlimited, never-metered owner
ADMIN_EMAILS=you@example.com
```

`apps/api/railway.json` already runs `alembic upgrade head` before each deploy and
healthchecks `/health` — nothing to add.

## 5. Configure the **worker** service

**+ New → GitHub Repo → same repo** → Settings:
- **Root Directory:** `apps/api`
- **Config-as-code / Railway Config File:** `railway.worker.json`  ← this makes it run
  `arq …` with no healthcheck (instead of the api config)
- **Variables:** same as the api service (copy them — it needs DB/Redis/Neo4j/Qdrant +
  `LLM_KEY_ENCRYPTION_KEY`). It has no public domain.

## 6. Configure the **web** service

**+ New → GitHub Repo → same repo** → Settings:
- **Root Directory:** `apps/web`
- **Variables** (the `NEXT_PUBLIC_*` are baked at **build** time — set them *before* the
  first deploy, then redeploy if you change them):

```
NEXT_PUBLIC_API_BASE_URL=https://api-production-xxxx.up.railway.app   # the api domain from step 4
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_live_...
CLERK_SECRET_KEY=sk_live_...      # clerkMiddleware needs it at runtime too
```

- **Networking → Generate Domain**, then **Custom Domain → `yourdomain.com`**. Railway
  shows a **CNAME target** — in **Cloudflare** add: `CNAME @ → that-target` and
  `CNAME www → that-target` (Cloudflare flattens the apex CNAME). Start **DNS-only (grey
  cloud)**; if you later enable the orange proxy, set SSL/TLS mode **Full (strict)**.

Then set the api's `CORS_ORIGINS` to `https://yourdomain.com` (your final web URL).

## 7. Deploy + verify

Deploy order doesn't matter much (Railway retries), but the clean path: Postgres/Redis/
Neo4j/Qdrant up → api (it migrates on deploy) → worker → web.

- Visit **https://yourdomain.com** → loads over HTTPS.
- `https://api-.../health` → `{"ok": true, ...}`.
- Sign up with your `ADMIN_EMAILS` address → owner/unlimited + Admin panel.

## 8. Register the webhooks (after the api has a public URL)

- **Clerk** dashboard → Webhooks → `https://<api-domain>/v1/webhooks/clerk` (subscribe to `user.*`).
- **Polar** dashboard → Webhooks → `https://<api-domain>/v1/billing/webhook/polar`.

## Updating

Just `git push` to `main` — Railway rebuilds + redeploys each affected service, and the
api re-runs `alembic upgrade head` automatically.

## Cost note

The 4 always-on datastores are the bulk of the bill. To trim cost you can enable
**serverless / app-sleep** on **web** and **api** (stateless — they cold-start in a few
seconds). Don't sleep the **worker** (it runs crons) or the databases (cold-starts are
slow/fragile, especially Neo4j). For the cheapest always-on full stack, a fixed VPS
(`DEPLOY.md`) is far less per month — but Railway wins on zero server management.
