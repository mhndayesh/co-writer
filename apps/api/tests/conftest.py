"""Test fixtures: in-memory SQLite + isolated env so each test session is clean.

Neo4j / Qdrant are intentionally left unconfigured so the graph and embedding
services exercise their fallback paths — that's the path most users will hit
before they wire up the optional services.
"""
import os

# Point at an in-memory SQLite (works with aiosqlite) BEFORE app modules are imported.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_gink.db")
os.environ.setdefault("JWT_SECRET", "test_secret_at_least_32_chars_long_xxxxxxxxx")
os.environ.setdefault("LLM_PROVIDER", "lmstudio")
os.environ.setdefault("LMSTUDIO_BASE_URL", "http://127.0.0.1:65535/v1")  # guaranteed-unreachable port
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
# Leave NEO4J_URI / QDRANT_URL unset → services fall back

import asyncio
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db.base import Base
from app.db.session import engine
from app.main import app


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture()
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
