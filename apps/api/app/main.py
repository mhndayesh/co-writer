from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.errors import AppError, envelope_err

log = logging.getLogger("gink")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("G-Ink API starting up")
    yield
    log.info("G-Ink API shutting down")


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="G-Ink Novel Studio API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(AppError)
    async def app_err_handler(_req: Request, exc: AppError):
        return envelope_err(exc.code, exc.message, details=exc.details, status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def fallback(_req: Request, exc: Exception):
        log.exception("Unhandled error: %s", exc)
        return envelope_err("internal_error", str(exc), status_code=500)

    @app.get("/health")
    async def health() -> dict:
        return {"ok": True, "data": {"status": "healthy"}}

    # Routers
    from app.api.v1 import (
        auth, stories, world, characters, chapters, flow, story_check,
        graph, rag, llm, locations, factions, scenes, threads, versions, export,
    )

    app.include_router(auth.router, prefix="/v1/auth", tags=["auth"])
    app.include_router(stories.router, prefix="/v1/stories", tags=["stories"])
    app.include_router(world.router, prefix="/v1/stories", tags=["world"])
    app.include_router(characters.router, prefix="/v1/stories", tags=["characters"])
    app.include_router(chapters.router, prefix="/v1/stories", tags=["chapters"])
    app.include_router(locations.router, prefix="/v1/stories", tags=["locations"])
    app.include_router(factions.router, prefix="/v1/stories", tags=["factions"])
    app.include_router(scenes.router, prefix="/v1/stories", tags=["scenes"])
    app.include_router(threads.router, prefix="/v1/stories", tags=["threads"])
    app.include_router(flow.router, prefix="/v1/stories", tags=["flow"])
    app.include_router(story_check.router, prefix="/v1/stories", tags=["story-check"])
    app.include_router(graph.router, prefix="/v1/stories", tags=["graph"])
    app.include_router(rag.router, prefix="/v1/stories", tags=["rag"])
    app.include_router(versions.router, prefix="/v1/stories", tags=["versions"])
    app.include_router(export.router, prefix="/v1/stories", tags=["export"])
    app.include_router(llm.router, prefix="/v1/llm", tags=["llm"])

    return app


app = create_app()
