import sys
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Anchor the .env to the api package root (apps/api/.env) so it loads no matter
# where uvicorn is launched from. Fixes the trap where running from a different
# cwd silently falls back to the default sqlite DB and creates an empty file.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./gink_dev.db"

    neo4j_uri: str | None = None
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""

    qdrant_url: str | None = None

    jwt_secret: str = "dev_only_change_me"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 60 * 8
    refresh_token_ttl_days: int = 7

    # ── Clerk auth ────────────────────────────────────────────────────────────
    # When clerk_jwks_url is set, get_current_user verifies RS256 session tokens
    # against Clerk's JWKS and maps them to local users by clerk_user_id. Legacy
    # HS256 tokens (tests / transition) still validate via jwt_secret — the path
    # is chosen per-request from the token's `alg` header.
    clerk_jwks_url: str = ""
    clerk_issuer: str = ""               # e.g. https://<subdomain>.clerk.accounts.dev
    clerk_secret_key: str = ""           # Backend API key (sk_...) — used to backfill email/name
    clerk_webhook_secret: str = ""       # Svix signing secret (whsec_...) for /v1/webhooks/clerk

    # The legacy email+password endpoints (/v1/auth/signup|login|refresh|logout)
    # are retired by default — Clerk owns sign-in/up. Kept mountable behind this
    # flag for the test suite (and any deployment mid-migration). HS256 tokens
    # still validate in get_current_user regardless of this flag.
    legacy_password_auth: bool = False

    @property
    def clerk_enabled(self) -> bool:
        return bool(self.clerk_jwks_url)

    llm_key_encryption_key: str = ""

    llm_provider: Literal["lmstudio", "openai", "anthropic", "openrouter", "gemini"] = "lmstudio"
    lmstudio_base_url: str = "http://localhost:1234/v1"
    lmstudio_model: str = "local-model"
    lmstudio_embed_model: str = "nomic-embed-text-v1.5"

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    openai_embed_model: str = "text-embedding-3-small"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5"

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openai/gpt-4o-mini"

    gemini_api_key: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    gemini_model: str = "gemini-2.0-flash"
    gemini_embed_model: str = "text-embedding-004"

    # ── House ("dev AI") model ────────────────────────────────────────────────
    # The provider the website itself pays for — used by the `free` trial and the
    # `dev_ai` tier. Its API key comes from the matching <provider>_api_key above
    # (e.g. system_llm_provider="openai" → openai_api_key). BYOK users never touch
    # this; they use only their own keys.
    system_llm_provider: Literal["lmstudio", "openai", "anthropic", "openrouter", "gemini"] = "lmstudio"

    # ── Subscription limits (TODO: real numbers — these are placeholders) ──────
    # A Dev-AI / free call is blocked when EITHER the action cap OR the token cap
    # for the period is reached. Tune via env without touching code.
    free_trial_max_actions: int = 15            # lifetime trial allowance
    free_trial_max_tokens: int = 50_000         # lifetime trial allowance
    dev_ai_max_actions_per_month: int = 500     # TODO
    dev_ai_max_tokens_per_month: int = 2_000_000  # TODO
    # BYOK is uncapped on our side (the user pays their own provider).

    # ── Billing (provider-agnostic) ───────────────────────────────────────────
    # "manual" activates instantly (admin / dev / test). "stripe" uses Stripe
    # Checkout + webhooks. New providers: add a BillingProvider in services/billing.
    billing_provider: Literal["manual", "stripe", "polar"] = "manual"
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_dev_ai: str = ""               # TODO: Stripe price id for Dev-AI
    stripe_price_byok: str = ""                 # TODO: Stripe price id for BYOK

    # ── Polar (Merchant of Record) ────────────────────────────────────────────
    # Polar is the seller of record, so it works for merchants in countries Stripe
    # doesn't directly support (e.g. Saudi Arabia). Set BILLING_PROVIDER=polar.
    polar_access_token: str = ""
    polar_webhook_secret: str = ""              # Standard Webhooks signing secret
    polar_server: Literal["sandbox", "production"] = "production"
    polar_product_dev_ai: str = ""              # Polar product id for the Plus tier
    polar_product_byok: str = ""                # Polar product id for the BYOK tier
    billing_success_url: str = "http://localhost:3000/settings?billing=success"
    billing_cancel_url: str = "http://localhost:3000/pricing?billing=cancel"

    # Comma-separated emails granted admin rights (plan overrides, support tools)
    # AND unlimited, never-metered AI — the site owner shouldn't have to subscribe
    # to their own product. MUST be set via the ADMIN_EMAILS env var.
    #
    # SECURITY: this is intentionally empty by default. A non-empty default would
    # silently grant admin to anyone who signs up with that address on every fresh
    # deployment (signup performs no email verification), which is a full account
    # takeover path. Set ADMIN_EMAILS explicitly for the deployments that need it.
    admin_emails: str = ""

    cors_origins: str = "http://localhost:3000"

    # Optional strict allowlist for BYOK provider base URLs. Empty (default) keeps
    # the permissive behavior (any public, non-private host is allowed — operators
    # may self-host OpenAI-compatible proxies). When set, only these hosts (plus the
    # built-in known providers) may be used — a hard SSRF lockdown for tighter envs.
    allowed_llm_hosts: str = ""

    # Production / observability
    # Constrained to known values so a typo (e.g. "Production") doesn't silently
    # toggle one guard on while leaving another off.
    environment: Literal["development", "staging", "production"] = "development"
    sentry_dsn: str = ""
    redis_url: str = ""
    max_request_body_mb: int = 10

    # ── Uploads (cover images) ────────────────────────────────────────────────
    # Where uploaded cover images are stored + served from. Blank → an `uploads`
    # dir anchored at the api package root (resolved in storage_service). In prod
    # this should be a mounted volume (docker-compose.prod.yml) or, later, swapped
    # for object storage. Images are served at /v1/uploads/<file> (same-origin).
    upload_dir: str = ""
    max_image_upload_mb: int = 5

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_llm_hosts_list(self) -> list[str]:
        return [h.strip().lower() for h in self.allowed_llm_hosts.split(",") if h.strip()]

    @property
    def admin_emails_list(self) -> list[str]:
        return [e.strip().lower() for e in self.admin_emails.split(",") if e.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    def validate_secrets(self) -> None:
        """Fail fast if insecure defaults reach any non-development environment.

        Only `development` is allowed to run with the weak defaults. `staging`
        and `production` must carry real secrets to prevent:
        - JWT forgery (short/default signing key)
        - BYOK keys stored plaintext (missing/invalid Fernet key)
        - Free unlimited AI (manual billing in non-dev)
        - Default credentials in shared infra (Neo4j dev password)
        - SQLite in production (data-loss, no concurrent writes)
        """
        if self.is_development:
            return

        env = self.environment

        def _fatal(msg: str) -> None:
            sys.exit(f"FATAL [{env}]: {msg}")

        if self.jwt_secret == "dev_only_change_me" or len(self.jwt_secret) < 32:
            _fatal("JWT_SECRET is unset or too weak (needs >= 32 random chars).")

        if not self.llm_key_encryption_key:
            _fatal("LLM_KEY_ENCRYPTION_KEY is not set (BYOK keys would be stored plaintext).")

        try:
            from cryptography.fernet import Fernet
            Fernet(self.llm_key_encryption_key.encode())
        except Exception:
            _fatal("LLM_KEY_ENCRYPTION_KEY is not a valid Fernet key.")

        if self.database_url.startswith("sqlite"):
            _fatal(
                "DATABASE_URL points at SQLite. Use PostgreSQL in non-development "
                "(SQLite has no concurrent-write support and no crash recovery)."
            )

        if self.neo4j_password in ("", "gink_dev_password"):
            _fatal(
                "NEO4J_PASSWORD is using the dev default. Set a strong password in "
                ".env.production before exposing Neo4j."
            )

        if self.billing_provider == "manual":
            _fatal(
                "BILLING_PROVIDER=manual activates any paid tier for free. "
                "Set BILLING_PROVIDER=stripe (or add Stripe config) before going live."
            )

        origins = self.cors_origins.strip()
        if origins == "*" or origins == "":
            _fatal(
                "CORS_ORIGINS is wildcard or empty. Set it to your actual frontend "
                "origin(s) to prevent credentialed cross-origin requests from any site."
            )

        if self.billing_provider == "stripe" and not (self.stripe_secret_key and self.stripe_webhook_secret):
            _fatal(
                "BILLING_PROVIDER=stripe but STRIPE_SECRET_KEY and/or STRIPE_WEBHOOK_SECRET "
                "are unset — checkout would fail and unsigned webhooks could be accepted."
            )

        if self.billing_provider == "polar" and not (self.polar_access_token and self.polar_webhook_secret):
            _fatal(
                "BILLING_PROVIDER=polar but POLAR_ACCESS_TOKEN and/or POLAR_WEBHOOK_SECRET "
                "are unset — checkout would fail and unsigned webhooks could be accepted."
            )

        if self.clerk_enabled and not self.clerk_issuer:
            _fatal(
                "CLERK_JWKS_URL is set but CLERK_ISSUER is not — issuer verification would "
                "be skipped, accepting validly-signed tokens from any Clerk tenant."
            )

        if self.legacy_password_auth:
            _fatal(
                "LEGACY_PASSWORD_AUTH=1 in a non-development environment exposes the "
                "unverified email/password endpoints — a full account-takeover path "
                "(sign up as an ADMIN_EMAILS address with no verification). Disable it "
                "and use Clerk in production."
            )

        if not self.clerk_enabled:
            _fatal(
                "No auth provider configured: set CLERK_JWKS_URL (+ CLERK_ISSUER) so users "
                "can actually sign in. Legacy password auth is disallowed in production."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
