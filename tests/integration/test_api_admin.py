"""Admin dashboard API — auth + the learning-loop reads (US-9, FR-17)."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from takshashila_chatbot.api.app import create_app
from takshashila_chatbot.application.admin_auth import AdminAuth
from takshashila_chatbot.application.answer_service import AnswerService
from takshashila_chatbot.application.dashboard import DashboardService
from takshashila_chatbot.application.dead_end_clustering import DeadEndClusteringService
from takshashila_chatbot.application.lead_service import LeadService
from takshashila_chatbot.application.ports import QuestionOutcome
from takshashila_chatbot.application.repositories import (
    InMemoryDeadEndClusterRepository,
    InMemoryLeadRepository,
    InMemoryQuestionLog,
)
from takshashila_chatbot.domain.auth import admin_user_from_password
from takshashila_chatbot.domain.clock import IST, FixedClock
from takshashila_chatbot.domain.rate_limit import RateLimiter
from takshashila_chatbot.testing.fakes import FakeLanguageModel, FakeRetriever, ScriptedEmbedder

pytestmark = pytest.mark.integration

TOKEN = "admin-secret"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def _build() -> TestClient:
    clock = FixedClock(dt.datetime(2026, 6, 16, 12, 0, tzinfo=IST))
    log = InMemoryQuestionLog(clock)
    log.record(QuestionOutcome("What is the hostel fee?", "dead_end", "fees", "en"))
    log.record(QuestionOutcome("hostel fees?", "dead_end", "fees", "en"))
    log.record(QuestionOutcome("library hours?", "dead_end", "facilities", "en"))

    cluster_repo = InMemoryDeadEndClusterRepository()
    lead_repo = InMemoryLeadRepository()
    embedder = ScriptedEmbedder(
        {
            "What is the hostel fee?": [1.0, 0.0],
            "hostel fees?": [0.99, 0.01],
            "library hours?": [0.0, 1.0],
        }
    )
    app = create_app(
        answer_service=AnswerService(FakeRetriever([]), FakeLanguageModel(), clock, outcome_sink=log),
        lead_service=LeadService(lead_repo, clock),
        rate_limiter=RateLimiter([(100, 60)], clock),
        dashboard_service=DashboardService(cluster_repo, log, lead_repo),
        clustering_service=DeadEndClusteringService(log, embedder, cluster_repo, threshold=0.9),
        admin_token=TOKEN,
    )
    return TestClient(app)


def test_admin_endpoints_require_a_valid_token():
    client = _build()
    assert client.get("/api/v1/admin/dashboard/dead-ends").status_code == 401
    bad = client.get("/api/v1/admin/dashboard/dead-ends", headers={"Authorization": "Bearer nope"})
    assert bad.status_code == 401


def test_cluster_then_dead_ends_ranked_by_frequency():  # AC-9.1
    client = _build()

    clustered = client.post("/api/v1/admin/cluster", headers=AUTH)
    assert clustered.status_code == 200
    assert clustered.json()["clustered"] == 2

    groups = client.get("/api/v1/admin/dashboard/dead-ends", headers=AUTH).json()["dead_ends"]
    assert groups[0]["frequency"] == 2
    assert "hostel" in groups[0]["question"].lower()


def test_stats_and_leads():  # AC-9.2
    client = _build()
    assert client.post(
        "/api/v1/leads", json={"name": "Asha", "email": "a@b.co", "consent": True}
    ).status_code == 201

    stats = client.get("/api/v1/admin/dashboard/stats", headers=AUTH).json()
    assert stats["questions_per_day"]["2026-06-16"] == 3
    assert stats["lead_count"] == 1
    assert stats["dead_end_count"] == 3  # all three seeded turns were dead-ends
    assert stats["answered_count"] == 0

    leads = client.get("/api/v1/admin/leads", headers=AUTH).json()["leads"]
    assert leads[0]["name"] == "Asha"


def _build_with_login() -> TestClient:
    clock = FixedClock(dt.datetime(2026, 6, 16, 12, 0, tzinfo=IST))
    log = InMemoryQuestionLog(clock)
    cluster_repo = InMemoryDeadEndClusterRepository()
    lead_repo = InMemoryLeadRepository()
    auth = AdminAuth(
        user=admin_user_from_password("admin", "s3cret", salt="admin"),
        secret="sign",
        clock=clock,
        ttl_seconds=3600,
    )
    app = create_app(
        answer_service=AnswerService(FakeRetriever([]), FakeLanguageModel(), clock, outcome_sink=log),
        lead_service=LeadService(lead_repo, clock),
        rate_limiter=RateLimiter([(100, 60)], clock),
        dashboard_service=DashboardService(cluster_repo, log, lead_repo),
        admin_auth=auth,
    )
    return TestClient(app)


def test_login_issues_a_token_that_unlocks_admin_endpoints():
    client = _build_with_login()
    # Without a token the dashboard is locked.
    assert client.get("/api/v1/admin/dashboard/stats").status_code == 401

    res = client.post("/api/v1/admin/login", json={"username": "admin", "password": "s3cret"})
    assert res.status_code == 200
    body = res.json()
    assert body["username"] == "admin" and body["expires_in"] == 3600
    token = body["token"]

    ok = client.get(
        "/api/v1/admin/dashboard/stats", headers={"Authorization": f"Bearer {token}"}
    )
    assert ok.status_code == 200


def test_login_with_bad_credentials_is_rejected():
    client = _build_with_login()
    res = client.post("/api/v1/admin/login", json={"username": "admin", "password": "nope"})
    assert res.status_code == 401


def test_cluster_endpoint_unavailable_without_clustering_service():
    clock = FixedClock(dt.datetime(2026, 6, 16, 12, 0, tzinfo=IST))
    log = InMemoryQuestionLog(clock)
    cluster_repo = InMemoryDeadEndClusterRepository()
    lead_repo = InMemoryLeadRepository()
    app = create_app(
        answer_service=AnswerService(FakeRetriever([]), FakeLanguageModel(), clock, outcome_sink=log),
        lead_service=LeadService(lead_repo, clock),
        rate_limiter=RateLimiter([(100, 60)], clock),
        dashboard_service=DashboardService(cluster_repo, log, lead_repo),
        clustering_service=None,
        admin_token=TOKEN,
    )
    assert TestClient(app).post("/api/v1/admin/cluster", headers=AUTH).status_code == 503
