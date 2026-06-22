"""Shared fixtures for API integration tests — builds the app with the factory
and injectable, deterministic collaborators."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from takshashila_chatbot.api.app import create_app
from takshashila_chatbot.application.answer_service import AnswerService
from takshashila_chatbot.application.lead_service import LeadService
from takshashila_chatbot.application.repositories import InMemoryLeadRepository
from takshashila_chatbot.domain.clock import IST, FixedClock
from takshashila_chatbot.domain.rate_limit import RateLimiter
from takshashila_chatbot.domain.retrieval import RetrievedChunk
from takshashila_chatbot.testing.fakes import FakeLanguageModel, FakeRetriever

FEE_CHUNK = RetrievedChunk(
    chunk_id="c1",
    document_id="fees-doc",
    text="The B.Tech CSE fee is INR 1,50,000 per year.",
    topic="fees",
    score=0.92,
    metadata={"due_date": "2026-12-31"},
)


@pytest.fixture
def clock():
    return FixedClock(dt.datetime(2026, 6, 15, 12, 0, tzinfo=IST))


@pytest.fixture
def lead_repo():
    return InMemoryLeadRepository()


@pytest.fixture
def make_client(clock, lead_repo):
    def _make(*, chunks=(FEE_CHUNK,), llm=None, rate_limiter=None, answer_service=None):
        service = answer_service or AnswerService(
            FakeRetriever(list(chunks)), llm or FakeLanguageModel(), clock
        )
        leads = LeadService(lead_repo, clock)
        limiter = rate_limiter or RateLimiter([(15, 60), (100, 3600)], clock)
        app = create_app(answer_service=service, lead_service=leads, rate_limiter=limiter)
        return TestClient(app)

    return _make
