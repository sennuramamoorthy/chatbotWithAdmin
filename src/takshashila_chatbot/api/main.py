"""Dev/demo entrypoint — NOT production wiring.

Serves the API with in-memory, non-durable adapters, seeded from the real
admissions data in ``data/admissions.db`` (see ``ingest/admissions_db.py``), so the
whole system — grounded answers, the learning loop, content publishing — is runnable
with one command before the self-hosted LLM + pgvector adapters land. Run:

    make run
    # or
    uvicorn takshashila_chatbot.api.main:app --reload

The in-memory chunk store doubles as the retriever and the publish target, so
publishing content via /admin/content makes it answerable immediately — the loop.
Retrieval here is keyword-based (no embeddings); production uses pgvector semantics.
"""

from __future__ import annotations

from pathlib import Path

from ..adapters.log_email_sender import LogEmailSender
from ..application.admin_auth import AdminAuth
from ..application.answer_service import AnswerService
from ..application.answer_stream import AnswerStreamService
from ..application.content_service import ContentService
from ..application.dashboard import DashboardService
from ..application.dead_end_clustering import DeadEndClusteringService
from ..application.lead_delivery import InMemoryOutboxStore, LeadDeliveryService
from ..application.lead_service import LeadService
from ..application.repositories import (
    InMemoryChunkStore,
    InMemoryContentRepository,
    InMemoryDeadEndClusterRepository,
    InMemoryLeadRepository,
    InMemoryQuestionLog,
)
from ..application.session import InMemorySessionStore, SessionMemory
from ..domain.auth import admin_user_from_password
from ..domain.clock import SystemClock
from ..domain.rate_limit import RateLimiter
from ..ingest.admissions_db import read_admissions_db
from ..testing.fakes import FakeLanguageModel, HashingEmbedder
from .app import create_app

_ADMISSIONS_DB = Path(__file__).resolve().parents[3] / "data" / "admissions.db"


def build_app():
    clock = SystemClock()
    log = InMemoryQuestionLog(clock)
    cluster_repo = InMemoryDeadEndClusterRepository()
    lead_repo = InMemoryLeadRepository()
    embedder = HashingEmbedder()  # demo only; production uses HttpEmbedder

    chunk_store = InMemoryChunkStore()  # retriever AND publish target
    chunk_store.seed(read_admissions_db(str(_ADMISSIONS_DB)))  # real admissions data
    llm = FakeLanguageModel()

    # Demo login: username "admin" / password "takshashila". "demo-admin-token" stays
    # valid as a service/break-glass token; production sets these from the environment.
    admin_auth = AdminAuth(
        service_token="demo-admin-token",
        user=admin_user_from_password("admin", "takshashila", salt="admin"),
        secret="demo-admin-token",
        clock=clock,
    )

    return create_app(
        answer_service=AnswerService(chunk_store, llm, clock, outcome_sink=log),
        answer_stream_service=AnswerStreamService(chunk_store, llm, clock, outcome_sink=log),
        session_memory=SessionMemory(InMemorySessionStore(clock)),
        lead_delivery=LeadDeliveryService(InMemoryOutboxStore(), LogEmailSender()),
        lead_service=LeadService(lead_repo, clock),
        rate_limiter=RateLimiter([(15, 60), (100, 3600)], clock),
        dashboard_service=DashboardService(cluster_repo, log, lead_repo),
        clustering_service=DeadEndClusteringService(log, embedder, cluster_repo),
        content_service=ContentService(InMemoryContentRepository(), chunk_store, embedder, clock),
        admin_auth=admin_auth,
    )


app = build_app()
