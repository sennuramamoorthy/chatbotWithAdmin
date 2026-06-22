"""POST /api/v1/chat — SSE streaming, rate limiting, and soft-fail."""

import datetime as dt
import json

import pytest

from takshashila_chatbot.application.answer_service import AnswerService
from takshashila_chatbot.domain.rate_limit import RateLimiter
from takshashila_chatbot.domain.retrieval import RetrievedChunk
from takshashila_chatbot.testing.fakes import FakeRetriever

pytestmark = pytest.mark.integration


def _parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.strip().split("\n\n"):
        block = block.strip()
        if block.startswith("data:"):
            events.append(json.loads(block[len("data:") :].strip()))
    return events


def _tokens(events: list[dict]) -> str:
    return "".join(e["text"] for e in events if e["type"] == "token")


def _done(events: list[dict]) -> dict:
    return next(e for e in events if e["type"] == "done")


def test_grounded_answer_streams_with_metadata(make_client):  # TC-001 over HTTP
    response = make_client().post(
        "/api/v1/chat", json={"message": "What is the B.Tech CSE fee?", "session_id": "s1"}
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(response.text)
    assert "1,50,000" in _tokens(events)
    done = _done(events)
    assert done["outcome"] == "answered"
    assert "fees-doc" in done["citations"]
    assert done["offer_lead"] is False


def test_unknown_question_falls_back(make_client):  # TC-002 over HTTP
    weak = RetrievedChunk("c2", "d2", "unrelated", "facilities", 0.2)
    response = make_client(chunks=(weak,)).post(
        "/api/v1/chat", json={"message": "What's the hostel fee?", "session_id": "s2"}
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    done = _done(events)
    assert done["outcome"] == "dead_end"
    assert done["offer_lead"] is True
    assert "Admissions" in _tokens(events)


def test_empty_message_is_invalid_input(make_client):  # TC-037 over HTTP
    response = make_client().post(
        "/api/v1/chat", json={"message": "   ", "session_id": "s3"}
    )
    assert response.status_code == 200
    assert _done(_parse_sse(response.text))["outcome"] == "invalid_input"


def test_rate_limited_returns_429(make_client, clock):  # TC-027 over HTTP
    limiter = RateLimiter([(2, 60)], clock)
    client = make_client(rate_limiter=limiter)
    payload = {"message": "What is the fee?", "session_id": "s4"}

    for _ in range(2):
        assert client.post("/api/v1/chat", json=payload).status_code == 200

    blocked = client.post("/api/v1/chat", json=payload)
    assert blocked.status_code == 429
    assert "retry_after" in blocked.json()


def test_soft_fails_when_backend_errors(make_client, clock):  # TC-029
    class BoomLLM:
        def generate(self, request):
            raise RuntimeError("LLM unreachable")

    service = AnswerService(
        FakeRetriever([RetrievedChunk("c", "d", "B.Tech fee info.", "fees", 0.9)]),
        BoomLLM(),
        clock,
    )
    response = make_client(answer_service=service).post(
        "/api/v1/chat", json={"message": "What is the fee?", "session_id": "s5"}
    )
    assert response.status_code == 503
    body = response.json()
    assert body["contact"]["email"]  # static Admissions contact, not a blank/broken state
