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

    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
