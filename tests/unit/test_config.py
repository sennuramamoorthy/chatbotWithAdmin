"""Settings.from_env — environment parsing (pure, unit-tested)."""

import pytest

from takshashila_chatbot.config import Settings

pytestmark = pytest.mark.unit


def _env(**overrides) -> dict[str, str]:
    base = {"DATABASE_URL": "postgresql://localhost/db", "LLM_BASE_URL": "http://llm"}
    base.update(overrides)
    return base


def test_reads_required_and_applies_defaults():
    settings = Settings.from_env(_env())
    assert settings.database_url == "postgresql://localhost/db"
    assert settings.llm_base_url == "http://llm"
    assert settings.embeddings_base_url == "http://llm"  # defaults to the LLM base url
    assert settings.grounding_threshold == 0.6
    assert settings.rate_per_minute == 15
    assert settings.rate_per_hour == 100
    assert settings.admin_token == ""  # locked until configured
    assert settings.admin_username == "admin"
    assert settings.admin_password == ""  # no login until a password is set
    assert settings.admin_session_ttl_seconds == 28800  # 8h
    assert settings.cors_origins == ("*",)  # public widget embeds anywhere by default
    assert settings.redis_url == "redis://localhost:6379/0"


def test_overrides_and_parses_numbers():
    settings = Settings.from_env(
        _env(
            EMBEDDINGS_BASE_URL="http://emb",
            GROUNDING_THRESHOLD="0.75",
            RATE_PER_MINUTE="5",
            RATE_PER_HOUR="50",
            ADMIN_TOKEN="secret",
            ADMIN_USERNAME="root",
            ADMIN_PASSWORD="pw",
            ADMIN_SESSION_TTL_SECONDS="3600",
            CORS_ORIGINS="https://a.edu,https://b.edu",
            REDIS_URL="redis://cache:6379/1",
        )
    )
    assert settings.redis_url == "redis://cache:6379/1"
    assert settings.embeddings_base_url == "http://emb"
    assert settings.grounding_threshold == 0.75
    assert settings.rate_per_minute == 5
    assert settings.rate_per_hour == 50
    assert settings.admin_token == "secret"
    assert settings.admin_username == "root"
    assert settings.admin_password == "pw"
    assert settings.admin_session_ttl_seconds == 3600
    assert settings.cors_origins == ("https://a.edu", "https://b.edu")


def test_missing_required_raises():
    with pytest.raises(KeyError):
        Settings.from_env({"LLM_BASE_URL": "http://llm"})  # no DATABASE_URL
