import json
import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import get_settings
from app.core.errors import AppError, envelope_err


# ---------------------------------------------------------------------------
# Structured JSON logging
# ---------------------------------------------------------------------------

class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log = {
            "ts": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            log["exc"] = self.formatException(record.exc_info)
        return json.dumps(log)


_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(_JsonFormatter())
logging.root.handlers = [_handler]
logging.basicConfig(level=logging.INFO)

log = logging.getLogger("gink")


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    s.validate_secrets()
    log.info("G-Ink API starting up", extra={"environment": s.environment})
    yield
    log.info("G-Ink API shutting down")
    # ── Teardown: release pooled connections and optional service clients so a
    # reload/restart doesn't leak DB connections or Neo4j/Qdrant sockets. ──
    try:
        from app.db.session import engine
        await engine.dispose()
    except Exception:
        log.warning("DB engine dispose failed", exc_info=True)
    try:
        from app.services import graph_service
        await graph_service.close_driver()
    except Exception:
        log.warning("Neo4j driver close failed", exc_info=True)
    try:
        from app.services import embedding_service
        await embedding_service.close_client()
    except Exception:
        log.warning("Qdrant client close failed", exc_info=True)


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    s = get_settings()
    # Don't expose interactive docs / the OpenAPI schema in production.
    _docs = (
        {"docs_url": None, "redoc_url": None, "openapi_url": None}
        if s.environment == "production"
        else {}
    )
    app = FastAPI(title="G-Ink Novel Studio API", version="0.1.0", lifespan=lifespan, **_docs)

    # ── CORS ────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Security + size middleware ───────────────────────────────────────────
    from app.core.middleware import (
        SecurityHeadersMiddleware,
        RequestSizeLimitMiddleware,
        RequestBodyTooLarge,
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestSizeLimitMiddleware, max_bytes=s.max_request_body_mb * 1024 * 1024)

    @app.exception_handler(RequestBodyTooLarge)
    async def body_too_large_handler(_req: Request, _exc: RequestBodyTooLarge):
        return envelope_err("payload_too_large", "Request body exceeds size limit", status_code=413)

    # ── Rate limiting ────────────────────────────────────────────────────────
    # The shared limiter (app/core/ratelimit.py) is imported here AND by route
    # modules for per-route limits. SlowAPIMiddleware is what actually ENFORCES
    # the limits — without it the limiter is a no-op (default_limits never apply).
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware

    from app.core.ratelimit import limiter
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # ── Sentry ───────────────────────────────────────────────────────────────
    if s.sentry_dsn:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        sentry_sdk.init(
            dsn=s.sentry_dsn,
            environment=s.environment,
            integrations=[FastApiIntegration(), SqlalchemyIntegration()],
            traces_sample_rate=0.1,
        )

    # ── Exception handlers ────────────────────────────────────────────────
    @app.exception_handler(AppError)
    async def app_err_handler(_req: Request, exc: AppError):
        return envelope_err(exc.code, exc.message, details=exc.details, status_code=exc.status_code)

    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.orm.exc import StaleDataError

    @app.exception_handler(StaleDataError)
    async def stale_data_handler(_req: Request, exc: StaleDataError):
        # version_id_col mismatch → someone else edited this row since we read it.
        log.info("optimistic-lock conflict: %s", exc)
        return envelope_err(
            "conflict",
            "This was changed in another tab or session. Reload to get the latest version, then reapply your edit.",
            status_code=409,
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(_req: Request, exc: IntegrityError):
        # Check-then-act races (e.g. two requests both creating a row that a unique
        # constraint forbids) surface here. Return a retryable 409 rather than a raw
        # 500, but log the underlying error so genuine constraint bugs stay visible.
        log.warning("integrity error → 409: %s", exc)
        return envelope_err(
            "conflict",
            "That action conflicted with a concurrent change. Please retry.",
            status_code=409,
        )

    @app.exception_handler(Exception)
    async def fallback(_req: Request, exc: Exception):
        log.exception("Unhandled error: %s", exc)
        return envelope_err("internal_error", "An unexpected error occurred", status_code=500)

    # ── Health endpoint ───────────────────────────────────────────────────
    @app.get("/health")
    async def health() -> dict:
        from app.db.session import SessionLocal
        checks: dict[str, bool] = {"api": True, "db": False}

        try:
            async with SessionLocal() as db:
                await db.execute(text("SELECT 1"))
            checks["db"] = True
        except Exception:
            pass

        try:
            # Reuse graph_service's cached, AUTHENTICATED driver. Building a fresh
            # driver here (a) omitted auth, so a secured Neo4j always reported
            # neo4j=false, and (b) let anonymous /health callers churn connections.
            from app.services import graph_service
            drv = graph_service._get_driver()
            if drv is not None:
                await drv.verify_connectivity()
                checks["neo4j"] = True
            else:
                checks["neo4j"] = None  # type: ignore[assignment]
        except Exception:
            checks["neo4j"] = False  # type: ignore[assignment]

        ok = checks["api"] and checks["db"]
        return {"ok": ok, "data": checks}

    # ── Existing routers ──────────────────────────────────────────────────
    from app.api.v1 import (
        auth, stories, world, characters, chapters, flow, story_check,
        graph, rag, llm, locations, factions, scenes, threads, narrative, versions, export,
        profile, billing, admin, clerk_webhook, identity, observer,
    )

    app.include_router(auth.router,        prefix="/v1/auth",    tags=["auth"])
    app.include_router(clerk_webhook.router, prefix="/v1/webhooks", tags=["webhooks"])
    # Legacy password endpoints stay retired unless explicitly re-enabled.
    if s.legacy_password_auth:
        from app.api.v1 import auth_legacy
        app.include_router(auth_legacy.router, prefix="/v1/auth", tags=["auth-legacy"])
    app.include_router(billing.router,     prefix="/v1/billing", tags=["billing"])
    app.include_router(admin.router,       prefix="/v1/admin",   tags=["admin"])
    app.include_router(stories.router,     prefix="/v1/stories", tags=["stories"])
    app.include_router(world.router,       prefix="/v1/stories", tags=["world"])
    app.include_router(characters.router,  prefix="/v1/stories", tags=["characters"])
    app.include_router(chapters.router,    prefix="/v1/stories", tags=["chapters"])
    app.include_router(locations.router,   prefix="/v1/stories", tags=["locations"])
    app.include_router(factions.router,    prefix="/v1/stories", tags=["factions"])
    app.include_router(scenes.router,      prefix="/v1/stories", tags=["scenes"])
    app.include_router(threads.router,     prefix="/v1/stories", tags=["threads"])
    app.include_router(narrative.router,   prefix="/v1/stories", tags=["narrative"])
    app.include_router(flow.router,        prefix="/v1/stories", tags=["flow"])
    app.include_router(identity.router,    prefix="/v1/stories", tags=["identity"])
    app.include_router(observer.router,    prefix="/v1/stories", tags=["observer"])
    app.include_router(story_check.router, prefix="/v1/stories", tags=["story-check"])
    app.include_router(graph.router,       prefix="/v1/stories", tags=["graph"])
    app.include_router(rag.router,         prefix="/v1/stories", tags=["rag"])
    app.include_router(versions.router,    prefix="/v1/stories", tags=["versions"])
    app.include_router(export.router,      prefix="/v1/stories", tags=["export"])
    app.include_router(llm.router,         prefix="/v1/llm",     tags=["llm"])
    app.include_router(profile.router,     prefix="/v1/u",       tags=["profile"])

    # ── Publishing platform routers ────────────────────────────────────────
    from app.routers.publishing import router as publishing_router
    from app.routers.reader     import reader_router
    from app.routers.social     import social_router
    from app.routers.export_pub import export_router as pub_export_router
    from app.routers.inbox      import inbox_router

    app.include_router(publishing_router, prefix="/v1/publish", tags=["publishing"])
    app.include_router(reader_router,     prefix="/v1/read",    tags=["reader"])
    app.include_router(social_router,     prefix="/v1/social",  tags=["social"])
    app.include_router(pub_export_router, prefix="/v1/export",  tags=["pub-export"])
    app.include_router(inbox_router,      prefix="/v1/inbox",   tags=["inbox"])

    # ── Async export (submit-and-poll for PDF/EPUB) ────────────────────────
    from app.api.v1.export_async import router as export_async_router
    app.include_router(export_async_router, prefix="/v1/export", tags=["export-async"])

    # ── Uploads + notifications ────────────────────────────────────────────
    from app.api.v1 import uploads, notifications
    app.include_router(uploads.router,       prefix="/v1/uploads",       tags=["uploads"])
    app.include_router(notifications.router, prefix="/v1/notifications", tags=["notifications"])

    # Serve uploaded cover images (same-origin, so the reader CSP's img-src 'self'
    # covers them). Mounted on a distinct path from the upload route above.
    from fastapi.staticfiles import StaticFiles
    from app.services import storage_service
    app.mount("/v1/media", StaticFiles(directory=str(storage_service.resolve_upload_dir())), name="media")

    return app


app = create_app()
