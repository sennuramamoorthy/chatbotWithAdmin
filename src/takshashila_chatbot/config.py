"""Runtime configuration from environment variables.

Required: ``DATABASE_URL``, ``LLM_BASE_URL``. Everything else has a sensible
default (embeddings default to the LLM base url for a single combined server).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .domain.retrieval import DEFAULT_GROUNDING_THRESHOLD


@dataclass(frozen=True)
class Settings:
    database_url: str
    llm_base_url: str
    embeddings_base_url: str
    llm_model: str = "local-llm"
    embeddings_model: str = "local-embeddings"
    grounding_threshold: float = DEFAULT_GROUNDING_THRESHOLD
    rate_per_minute: int = 15
    rate_per_hour: int = 100
    admin_token: str = ""  # service/break-glass token + session-signing secret
    admin_username: str = "admin"  # interactive login username
    admin_password: str = ""  # empty -> username/password login is disabled
    admin_session_ttl_seconds: int = 8 * 3600  # login session lifetime
    cors_origins: tuple[str, ...] = ("*",)
    redis_url: str = "redis://localhost:6379/0"

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> Settings:
        llm_base_url = environ["LLM_BASE_URL"]
        return cls(
            database_url=environ["DATABASE_URL"],
            llm_base_url=llm_base_url,
            embeddings_base_url=environ.get("EMBEDDINGS_BASE_URL", llm_base_url),
            llm_model=environ.get("LLM_MODEL", "local-llm"),
            embeddings_model=environ.get("EMBEDDINGS_MODEL", "local-embeddings"),
            grounding_threshold=float(
                environ.get("GROUNDING_THRESHOLD", str(DEFAULT_GROUNDING_THRESHOLD))
            ),
            rate_per_minute=int(environ.get("RATE_PER_MINUTE", "15")),
            rate_per_hour=int(environ.get("RATE_PER_HOUR", "100")),
            admin_token=environ.get("ADMIN_TOKEN", ""),
            admin_username=environ.get("ADMIN_USERNAME", "admin"),
            admin_password=environ.get("ADMIN_PASSWORD", ""),
            admin_session_ttl_seconds=int(environ.get("ADMIN_SESSION_TTL_SECONDS", "28800")),
            cors_origins=tuple(environ.get("CORS_ORIGINS", "*").split(",")),
            redis_url=environ.get("REDIS_URL", "redis://localhost:6379/0"),
        )
