"""Integration of session memory, true streaming, and the lead outbox into the API."""

import datetime as dt
import json

import pytest
from fastapi.testclient import TestClient

from takshashila_chatbot.adapters.log_email_sender import LogEmailSender
from takshashila_chatbot.api.app import create_app
from takshashila_chatbot.application.answer_service import AnswerResult, Outcome
from takshashila_chatbot.application.lead_delivery import (
    InMemoryOutboxStore,
    LeadDeliveryService,
)
from takshashila_chatbot.application.lead_service import LeadService
from takshashila_chatbot.application.repositories import InMemoryLeadRepository
from takshashila_chatbot.application.session import InMemorySessionStore, SessionMemory
from takshashila_chatbot.domain.clock import IST, FixedClock
from takshashila_chatbot.domain.rate_limit import RateLimiter

pytestmark = pytest.mark.integration


def _clock():
    return FixedClock(dt.datetime(2026, 6, 16, 12, 0, tzinfo=IST))


def _events(text: str) -> list[dict]:
    out = []
    for block in text.strip().split("\n\n"):
        block = block.strip()
        if block.startswith("data:"):
            out.append(json.loads(block[len("data:") :].strip()))
    return out


def _tokens(events: list[dict]) -> str:
    return "".join(e["text"] for e in events if e["type"] == "token")


def _done(events: list[dict]) -> dict:
    return next(e for e in events if e["type"] == "done")


class RecordingAnswer:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def answer(self, query: str) -> AnswerResult:
        self.queries.append(query)
        return AnswerResult(Outcome.ANSWERED, f"reply to {query}", language="en")


class FakeStream:
    def __init__(self, events: list[dict]) -> None:
        self._events = events
        self.queries: list[str] = []

    def stream(self, query: str):
        self.queries.append(query)
        yield from self._events


class BoomStream:
    def stream(self, query: str):
        yield {"type": "token", "text": "partial "}
        raise RuntimeError("llm down")


def _leads(clock):
    return LeadService(InMemoryLeadRepository(), clock)


def test_session_context_rewrites_a_bare_followup():  # TC-015 over HTTP
    clock = _clock()
    answer = RecordingAnswer()
    memory = SessionMemory(InMemorySessionStore(clock))
    client = TestClient(
        create_app(
            answer_service=answer,
            lead_service=_leads(clock),
            rate_limiter=RateLimiter([(100, 60)], clock),
            session_memory=memory,
        )
    )

    client.post("/api/v1/chat", json={"message": "What is the B.Tech CSE fee?", "session_id": "s"})
    client.post("/api/v1/chat", json={"message": "and the M.Tech?", "session_id": "s"})

    assert "B.Tech" in answer.queries[1]  # follow-up carried the prior subject


def test_streaming_path_streams_tokens_and_records_turns():
    clock = _clock()
    store = InMemorySessionStore(clock)
    stream = FakeStream(
        [
            {"type": "token", "text": "Hello "},
            {"type": "token", "text": "world"},
            {"type": "done", "outcome": "answered", "offer_lead": False},
        ]
    )
    client = TestClient(
        create_app(
            answer_service=RecordingAnswer(),
            lead_service=_leads(clock),
            rate_limiter=RateLimiter([(100, 60)], clock),
            answer_stream_service=stream,
            session_memory=SessionMemory(store),
        )
    )

    response = client.post("/api/v1/chat", json={"message": "hi", "session_id": "s"})
    assert _tokens(_events(response.text)) == "Hello world"
    assert len(store.load("s")) == 2  # user + bot turns recorded after streaming


def test_streaming_path_without_session_memory():
    clock = _clock()
    stream = FakeStream([{"type": "token", "text": "Hi"}, {"type": "done", "outcome": "answered"}])
    client = TestClient(
        create_app(
            answer_service=RecordingAnswer(),
            lead_service=_leads(clock),
            rate_limiter=RateLimiter([(100, 60)], clock),
            answer_stream_service=stream,
        )
    )
    response = client.post("/api/v1/chat", json={"message": "hi", "session_id": "s"})
    assert "Hi" in _tokens(_events(response.text))


def test_streaming_path_soft_fails_in_band_on_error():  # TC-029 (streaming variant)
    clock = _clock()
    client = TestClient(
        create_app(
            answer_service=RecordingAnswer(),
            lead_service=_leads(clock),
            rate_limiter=RateLimiter([(100, 60)], clock),
            answer_stream_service=BoomStream(),
        )
    )
    response = client.post("/api/v1/chat", json={"message": "hi", "session_id": "s"})
    events = _events(response.text)
    assert "partial" in _tokens(events)
    assert "unavailable" in _tokens(events).lower()
    assert _done(events)["outcome"] == "error"


def test_lead_submission_enqueues_delivery():  # FR-13 / EC-18
    clock = _clock()
    outbox = InMemoryOutboxStore()
    client = TestClient(
        create_app(
            answer_service=RecordingAnswer(),
            lead_service=_leads(clock),
            rate_limiter=RateLimiter([(100, 60)], clock),
            lead_delivery=LeadDeliveryService(outbox, LogEmailSender()),
        )
    )

    response = client.post(
        "/api/v1/leads", json={"name": "Asha", "email": "a@b.co", "consent": True}
    )
    assert response.status_code == 201
    assert len(outbox.pending()) == 1  # queued for async delivery
