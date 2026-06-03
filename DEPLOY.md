# Deploy G-Ink Co-Writer on a Docker VPS (Hetzner + Cloudflare)

This runs the whole stack from `docker-compose.prod.yml` on one server. Caddy
terminates TLS and routes your domain (`/v1/*` → api, everything else → web).
Single domain — the frontend and API share one origin, so there's nothing else to
wire.

> Sizing: the full stack (Postgres + Redis + **Neo4j + Qdrant** + api + web +
> worker + Caddy) wants **~8 GB RAM**. On Hetzner that's **CPX31** (or CX32). If you
> want a cheaper 4 GB box first, you can run without Neo4j/Qdrant (the app degrades:
> graph falls back to a Postgres view, vector search turns off) — see the bottom.

---

## 1. Create the server (Hetzner Cloud)

1. Hetzner Cloud Console → **+ New Project** → open it → **Add Server**.
2. **Location:** a EU region (Falkenstein/Nuremberg/Helsinki) is fine for Saudi latency.
3. **Image:** Ubuntu 24.04.
4. **Type:** Shared vCPU → **CPX31** (4 vCPU / 8 GB).
5. **SSH key:** add your public key (recommended). On your laptop: `ssh-keygen -t ed25519`
   then paste `~/.ssh/id_ed25519.pub`. (Or use a root password.)
6. **Firewall:** create one allowing inbound **22 (SSH), 80 (HTTP), 443 (HTTPS)**.
7. Create. Note the server's **public IP** (e.g. `5.75.x.x`).

## 2. Point your domain (Cloudflare)

In Cloudflare → your domain → **DNS** → add records pointing at the server IP:

| Type | Name | Content | Proxy |
|---|---|---|---|
| A | `@` | `YOUR_SERVER_IP` | **DNS only (grey cloud)** |
| A | `www` | `YOUR_SERVER_IP` | DNS only (grey cloud) |

> Start **DNS only (grey cloud)** so Caddy can get its Let's Encrypt certificate. Once
> the site is live over HTTPS you may switch the proxy on (orange cloud) — if you do,
> set Cloudflare SSL/TLS mode to **Full (strict)**, or you'll get a redirect loop.

## 3. SSH in + install Docker

```bash
ssh root@YOUR_SERVER_IP
curl -fsSL https://get.docker.com | sh          # installs Docker + compose plugin
docker compose version                           # sanity check
```

## 4. Get the code

```bash
git clone https://github.com/mhndayesh/co-writer.git
cd co-writer
```

## 5. Fill in your secrets

Create `.env.production` (one file holds everything). Generate the two crypto secrets:

```bash
# JWT secret (legacy auth / signing)
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
# BYOK encryption key (Fernet) — encrypts users' provider keys at rest
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Then write `.env.production` (replace every `CHANGE_ME`):

```dotenv
# ── Domain + deploy ─────────────────────────────────────────────
DOMAIN=yourdomain.com
NEXT_PUBLIC_API_BASE_URL=https://yourdomain.com     # same origin — Caddy routes /v1
ENVIRONMENT=production

# ── Datastores (any strong passwords) ───────────────────────────
POSTGRES_USER=gink
POSTGRES_PASSWORD=CHANGE_ME_strong_password
POSTGRES_DB=gink
NEO4J_USER=neo4j
NEO4J_PASSWORD=CHANGE_ME_strong_password
REDIS_URL=redis://redis:6379

# ── Security (paste the generated values) ───────────────────────
JWT_SECRET=CHANGE_ME_token_urlsafe_64
LLM_KEY_ENCRYPTION_KEY=CHANGE_ME_fernet_key

# ── Auth (Clerk) ────────────────────────────────────────────────
CLERK_JWKS_URL=https://clerk.yourdomain.com/.well-known/jwks.json
CLERK_ISSUER=https://clerk.yourdomain.com
CLERK_SECRET_KEY=sk_live_CHANGE_ME
CLERK_WEBHOOK_SECRET=whsec_CHANGE_ME
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_live_CHANGE_ME

# ── CORS (same domain) ──────────────────────────────────────────
CORS_ORIGINS=https://yourdomain.com

# ── House AI ("dev_ai"/Plus tier) — the key the site pays with ──
SYSTEM_LLM_PROVIDER=openai          # or anthropic / openrouter / gemini / lmstudio
OPENAI_API_KEY=CHANGE_ME            # set the key matching SYSTEM_LLM_PROVIDER
# DeepSeek (OpenAI-compatible) example:
# SYSTEM_LLM_PROVIDER=openai
# OPENAI_BASE_URL=https://api.deepseek.com/v1
# OPENAI_MODEL=deepseek-chat
# OPENAI_API_KEY=sk-...deepseek...

# ── Billing (Polar — Merchant of Record) ────────────────────────
BILLING_PROVIDER=polar
POLAR_ACCESS_TOKEN=CHANGE_ME
POLAR_WEBHOOK_SECRET=CHANGE_ME
POLAR_SERVER=production             # `sandbox` while testing
POLAR_PRODUCT_DEV_AI=CHANGE_ME      # Plus  ($19.99) product id
POLAR_PRODUCT_BYOK=CHANGE_ME        # BYOK  ($4.99) product id
BILLING_SUCCESS_URL=https://yourdomain.com/settings?billing=success
BILLING_CANCEL_URL=https://yourdomain.com/pricing?billing=cancel

# ── Admin / owner (your email = unlimited, never metered) ───────
ADMIN_EMAILS=you@example.com
```

Then make Compose read the same file for its `${...}` substitution:

```bash
cp .env.production .env
```

## 6. Build + launch

```bash
# 1) start the datastores
docker compose -f docker-compose.prod.yml up -d --build postgres redis neo4j qdrant
# 2) create the database schema (run once + after every update with new migrations)
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
# 3) start everything (api, web, worker, caddy)
docker compose -f docker-compose.prod.yml up -d --build
```

Watch it come up: `docker compose -f docker-compose.prod.yml logs -f caddy api web`

## 7. Verify

- Visit **https://yourdomain.com** — the site should load over HTTPS (Caddy auto-fetched the cert).
- `curl https://yourdomain.com/health` → `{"ok": true, ...}`.
- Sign up with your `ADMIN_EMAILS` address → you get owner/unlimited access + the Admin panel.

---

## Updating later

```bash
cd co-writer
git pull
cp .env.production .env                                            # if you changed env
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head   # if new migrations
docker compose -f docker-compose.prod.yml up -d --build
```

(Optional: the included `.github/workflows/ci.yml` automates this on every push —
it builds images, pushes to GHCR, and SSHes in to deploy. Set the `DEPLOY_HOST` /
`DEPLOY_SSH_KEY` secrets + `GITHUB_REPO` / `NEXT_PUBLIC_*` variables in GitHub to enable it.)

## Cheaper first run (4 GB box, no Neo4j/Qdrant)

The app runs fine without the graph + vector services (Graph-RAG features degrade
gracefully). To skip them, don't start those two services:

```bash
docker compose -f docker-compose.prod.yml up -d --build \
  postgres redis api web arq-worker caddy
```

Leave `NEO4J_URI` / `QDRANT_URL` unset (comment them out) and the api will use its
fallbacks. Add them later when you size up.

## Backups

A `backup` service runs `pg_dump` nightly with a restore-test (see `infra/backup.sh`).
For off-site copies set `BACKUP_OFFSITE_CMD` and `BACKUP_ALERT_WEBHOOK` in `.env.production`.
