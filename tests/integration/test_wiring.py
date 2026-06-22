"""Production wiring — drives the WHOLE real-adapter path with only the edges faked.

A single /chat call exercises: ConnectionExecutor → PgVectorRetriever (real SQL)
→ grounding gate → date enrichment → VllmLanguageModel (real HTTP) and HttpEmbedder
(real HTTP). /leads exercises PgLeadRepository. Only the DB connection and the two
HTTP endpoints are mocked.
"""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from takshashila_chatbot.config import Settings
from takshashila_chatbot.testing.fakes import FakeConnection
from takshashila_chatbot.wiring import build_app

pytestmark = pytest.mark.integration


def _settings() -> Settings:
    return Settings.from_env(
        {
            "DATABASE_URL": "postgresql://x",
            "LLM_BASE_URL": "http://llm",
            "LLM_MODEL": "llama",
            "ADMIN_TOKEN": "adm",
        }
    )


def _db_router(sql: str, params: tuple):
    if "kb_chunks" in sql:  # similarity search
        return (
            [
                (
                    "c1", "fees-doc",
                    "The B.Tech CSE fee is INR 1,50,000 per year.", "fees",
                    {"due_date": "2026-12-31"}, 0.95,
                )
            ],
            [("col",)],
        )
    if "INSERT INTO leads" in sql:
        return ([(1,)], [("id",)])
    return ([], None)


_LLM_CONTENT = "The B.Tech CSE fee is INR 1,50,000 per year."


def _llm_client() -> httpx.Client:
    def handler(request):
        body = json.loads(request.content)
        if body.get("stream"):  # production /chat streams: return OpenAI-style SSE deltas
            sse = "".join(
                f'data: {{"choices":[{{"delta":{{"content":"{word} "}}}}]}}\n\n'
                for word in _LLM_CONTENT.split()
            )
            sse += "data: [DONE]\n\n"
            return httpx.Response(
                200, content=sse.encode(), headers={"content-type": "text/event-stream"}
            )
        return httpx.Response(200, json={"choices": [{"message": {"content": _LLM_CONTENT}}]})

    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://llm")


def _embeddings_client() -> httpx.Client:
    def handler(request):
        return httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2, 0.3]}]})

    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://emb")


def _client() -> TestClient:
    app = build_app(
        _settings(),
        connection=FakeConnection(_db_router),
        llm_client=_llm_client(),
        embeddings_client=_embeddings_client(),
    )
    return TestClient(app)


def test_chat_answers_from_db_retrieval_and_llm():
    response = _client().post(
        "/api/v1/chat", json={"message": "What is the B.Tech CSE fee?", "session_id": "s1"}
    )
    assert response.status_code == 200
    assert "1,50,000" in response.text
    assert '"outcome": "answered"' in response.text
    assert "fees-doc" in response.text  # citation from the retrieved chunk


def test_lead_persists_through_repository():
    response = _client().post(
        "/api/v1/leads", json={"name": "Asha", "email": "asha@example.com", "consent": True}
    )
    assert response.status_code == 201
    assert response.json()["lead_id"] == "1"  # id from INSERT ... RETURNING


def test_learning_loop_clusters_and_ranks_through_prod_wiring():
    def router(sql: str, params: tuple):
        low = sql.lower()
        if "where outcome = 'dead_end'" in low:
            return ([("hostel fee?",), ("hostel fees?",)], [("col",)])
        if "select representative_text" in low:  # ranked read
            return ([("hostel fee?", 2)], [("col",)])
        return ([], None)  # delete/insert clusters, log writes

    app = build_app(
        _settings(),
        connection=FakeConnection(router),
        llm_client=_llm_client(),
        embeddings_client=_embeddings_client(),
    )
    client = TestClient(app)
    auth = {"Authorization": "Bearer adm"}

    # Two dead-ends, same (mock) embedding -> one cluster of frequency 2.
    assert client.post("/api/v1/admin/cluster", headers=auth).json()["clustered"] == 1

    groups = client.get("/api/v1/admin/dashboard/dead-ends", headers=auth).json()["dead_ends"]
    assert groups[0]["frequency"] == 2


def test_content_save_and_publish_through_prod_wiring():
    doc_row = ("hostel", "fees", "Hostel", "Hostel fee is INR 60,000.",
               "Hostel fee is INR 60,000.", 1, None, {})

    def router(sql: str, params: tuple):
        low = sql.lower()
        if "from kb_documents" in low:  # publish reads the doc first
            return ([doc_row], [("col",)])
        if "insert into kb_documents" in low or "update kb_documents" in low:
            return ([doc_row], [("col",)])
        return ([], None)  # version insert, kb_chunks delete/insert

    app = build_app(
        _settings(),
        connection=FakeConnection(router),
        llm_client=_llm_client(),
        embeddings_client=_embeddings_client(),
    )
    client = TestClient(app)
    auth = {"Authorization": "Bearer adm"}

    saved = client.put(
        "/api/v1/admin/content/hostel",
        headers=auth,
        json={"topic": "fees", "title": "Hostel", "body": "Hostel fee is INR 60,000."},
    )
    assert saved.status_code == 200

    published = client.post("/api/v1/admin/content/hostel/publish", headers=auth).json()
    assert published["published_version"] == 1


def test_admin_username_password_login_through_prod_wiring():
    settings = Settings.from_env(
        {
            "DATABASE_URL": "postgresql://x",
            "LLM_BASE_URL": "http://llm",
            "ADMIN_TOKEN": "adm",
            "ADMIN_USERNAME": "root",
            "ADMIN_PASSWORD": "pw",
        }
    )
    app = build_app(
        settings,
        connection=FakeConnection(_db_router),
        llm_client=_llm_client(),
        embeddings_client=_embeddings_client(),
    )
    client = TestClient(app)

    res = client.post("/api/v1/admin/login", json={"username": "root", "password": "pw"})
    assert res.status_code == 200
    token = res.json()["token"]

    ok = client.get(
        "/api/v1/admin/dashboard/dead-ends", headers={"Authorization": f"Bearer {token}"}
    )
    assert ok.status_code == 200


def test_build_app_uses_injected_durable_stores():
    import datetime as dt

    from takshashila_chatbot.application.lead_delivery import InMemoryOutboxStore
    from takshashila_chatbot.application.session import InMemorySessionStore
    from takshashila_chatbot.domain.clock import IST, FixedClock

    clock = FixedClock(dt.datetime(2026, 6, 16, 12, 0, tzinfo=IST))
    outbox = InMemoryOutboxStore()  # stand-in for PgOutboxStore / RedisSessionStore
    app = build_app(
        _settings(),
        connection=FakeConnection(_db_router),
        llm_client=_llm_client(),
        embeddings_client=_embeddings_client(),
        clock=clock,
        session_store=InMemorySessionStore(clock),
        outbox_store=outbox,
    )
    response = TestClient(app).post(
        "/api/v1/leads", json={"name": "Asha", "email": "a@b.co", "consent": True}
    )
    assert response.status_code == 201
    assert len(outbox.pending()) == 1  # the injected outbox was used
