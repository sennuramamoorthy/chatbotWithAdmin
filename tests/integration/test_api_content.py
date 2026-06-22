"""Admin content API — edit, Publish, and the loop closing (US-8, TC-030/031)."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from takshashila_chatbot.api.app import create_app
from takshashila_chatbot.application.answer_service import AnswerService
from takshashila_chatbot.application.content_service import ContentService
from takshashila_chatbot.application.dashboard import DashboardService
from takshashila_chatbot.application.lead_service import LeadService
from takshashila_chatbot.application.repositories import (
    InMemoryChunkStore,
    InMemoryContentRepository,
    InMemoryDeadEndClusterRepository,
    InMemoryLeadRepository,
    InMemoryQuestionLog,
)
from takshashila_chatbot.domain.clock import IST, FixedClock
from takshashila_chatbot.domain.rate_limit import RateLimiter
from takshashila_chatbot.testing.fakes import FakeEmbedder, FakeLanguageModel

pytestmark = pytest.mark.integration

TOKEN = "admin-secret"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def _client():
    clock = FixedClock(dt.datetime(2026, 6, 16, 12, 0, tzinfo=IST))
    log = InMemoryQuestionLog(clock)
    chunk_store = InMemoryChunkStore()  # retriever and publish target
    lead_repo = InMemoryLeadRepository()
    cluster_repo = InMemoryDeadEndClusterRepository()
    app = create_app(
        answer_service=AnswerService(chunk_store, FakeLanguageModel(), clock, outcome_sink=log),
        lead_service=LeadService(lead_repo, clock),
        rate_limiter=RateLimiter([(100, 60)], clock),
        dashboard_service=DashboardService(cluster_repo, log, lead_repo),
        content_service=ContentService(InMemoryContentRepository(), chunk_store, FakeEmbedder(), clock),
        admin_token=TOKEN,
    )
    return TestClient(app), clock


def _ask(client: TestClient, question: str) -> str:
    return client.post("/api/v1/chat", json={"message": question, "session_id": "s"}).text


def test_get_unknown_content_is_404():
    client, _ = _client()
    assert client.get("/api/v1/admin/content/nope", headers=AUTH).status_code == 404


def test_publish_unknown_content_is_404():
    client, _ = _client()
    assert client.post("/api/v1/admin/content/ghost/publish", headers=AUTH).status_code == 404


def test_save_draft_then_publish_closes_the_loop():  # TC-030 / TC-031 / US-8
    client, clock = _client()

    # Initially this question can't be answered -> dead-end.
    assert '"outcome": "dead_end"' in _ask(client, "What is the hostel fee?")

    # Admin saves a draft — NOT live yet (TC-030 / EC-22).
    saved = client.put(
        "/api/v1/admin/content/hostel",
        headers=AUTH,
        json={"topic": "fees", "title": "Hostel", "body": "The hostel fee is INR 60,000 per year."},
    )
    assert saved.status_code == 200
    assert saved.json()["published_body"] is None
    assert '"outcome": "dead_end"' in _ask(client, "What is the hostel fee?")

    fetched = client.get("/api/v1/admin/content/hostel", headers=AUTH)
    assert fetched.status_code == 200
    assert fetched.json()["draft_body"] == "The hostel fee is INR 60,000 per year."

    # Publish — re-indexes live and stamps the timestamp (TC-031 / AC-8.2/8.3).
    published = client.post("/api/v1/admin/content/hostel/publish", headers=AUTH).json()
    assert published["published_version"] == 1
    assert published["last_updated"] == clock.now().isoformat()

    # The bot now answers it — the loop is closed.
    answer = _ask(client, "What is the hostel fee?")
    assert '"outcome": "answered"' in answer
    assert "60,000" in answer
