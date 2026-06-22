"""Production composition root.

``build_app`` wires the real adapters but takes the connection and HTTP clients as
arguments, so the entire production path is testable with the edges mocked.
``build_app_from_env`` is the thin entrypoint that opens the real connections from
``Settings`` — run it with uvicorn's factory mode::

    DATABASE_URL=... LLM_BASE_URL=... \\
      uvicorn takshashila_chatbot.wiring:build_app_from_env --factory
"""

from __future__ import annotations

from typing import Any

import httpx

from .adapters.connection_executor import ConnectionExecutor
from .adapters.embeddings import HttpEmbedder
from .adapters.pg_chunk_writer import PgChunkWriter
from .adapters.pg_content_repository import PgContentRepository
from .adapters.pg_dead_end_cluster_repository import PgDeadEndClusterRepository
from .adapters.pg_lead_repository import PgLeadRepository
from .adapters.pg_question_log import PgQuestionLog
from .adapters.pgvector_retriever import PgVectorRetriever
from .adapters.vllm_llm import VllmLanguageModel
from .adapters.log_email_sender import LogEmailSender
from .adapters.pg_outbox import PgOutboxStore
from .adapters.redis_session import RedisSessionStore
from .api.app import create_app
from .application.admin_auth import AdminAuth
from .application.answer_service import AnswerService
from .application.answer_stream import AnswerStreamService
from .application.content_service import ContentService
from .application.dashboard import DashboardService
from .application.dead_end_clustering import DeadEndClusteringService
from .application.lead_delivery import InMemoryOutboxStore, LeadDeliveryService
from .application.lead_service import LeadService
from .application.session import InMemorySessionStore, SessionMemory
from .config import Settings
from .domain.auth import admin_user_from_password
from .domain.clock import Clock, SystemClock
from .domain.rate_limit import RateLimiter

# Similarity threshold for grouping dead-end questions (higher than the grounding
# threshold, which is a different decision).
_CLUSTER_THRESHOLD = 0.75


def build_app(
    settings: Settings,
    *,
    connection: Any,
    llm_client: httpx.Client,
    embeddings_client: httpx.Client,
    clock: Clock | None = None,
    session_store: Any | None = None,
    outbox_store: Any | None = None,
):
    clock = clock or SystemClock()
    executor = ConnectionExecutor(connection)
    # Durable stores when provided (Redis / Postgres), else per-process in-memory.
    session_store = session_store or InMemorySessionStore(clock)
    outbox_store = outbox_store or InMemoryOutboxStore()

    embedder = HttpEmbedder(embeddings_client, model=settings.embeddings_model)
    retriever = PgVectorRetriever(embedder, executor)
    llm = VllmLanguageModel(llm_client, model=settings.llm_model)
    question_log = PgQuestionLog(executor, clock)
    lead_repo = PgLeadRepository(executor)
    cluster_repo = PgDeadEndClusterRepository(executor)

    answer_service = AnswerService(
        retriever,
        llm,
        clock,
        outcome_sink=question_log,
        grounding_threshold=settings.grounding_threshold,
    )
    # vLLM adapter implements stream_tokens, so the chat endpoint streams for real.
    answer_stream_service = AnswerStreamService(
        retriever,
        llm,
        clock,
        outcome_sink=question_log,
        grounding_threshold=settings.grounding_threshold,
    )
    rate_limiter = RateLimiter(
        [(settings.rate_per_minute, 60), (settings.rate_per_hour, 3600)], clock
    )

    # Interactive username/password login is enabled only when a password is set;
    # the admin token doubles as the break-glass token and session-signing secret.
    admin_user = (
        admin_user_from_password(
            settings.admin_username, settings.admin_password, salt=settings.admin_username
        )
        if settings.admin_password
        else None
    )
    admin_auth = AdminAuth(
        service_token=settings.admin_token,
        user=admin_user,
        secret=settings.admin_token,
        clock=clock,
        ttl_seconds=settings.admin_session_ttl_seconds,
    )

    return create_app(
        answer_service=answer_service,
        lead_service=LeadService(lead_repo, clock),
        rate_limiter=rate_limiter,
        dashboard_service=DashboardService(cluster_repo, question_log, lead_repo),
        clustering_service=DeadEndClusteringService(
            question_log, embedder, cluster_repo, threshold=_CLUSTER_THRESHOLD
        ),
        content_service=ContentService(
            PgContentRepository(executor), PgChunkWriter(executor), embedder, clock
        ),
        answer_stream_service=answer_stream_service,
        session_memory=SessionMemory(session_store),
        lead_delivery=LeadDeliveryService(outbox_store, LogEmailSender()),
        admin_auth=admin_auth,
        cors_origins=settings.cors_origins,
    )


def build_app_from_env(environ: Any | None = None):  # pragma: no cover - real-infra glue
    import os

    import psycopg
    import redis

    settings = Settings.from_env(environ or os.environ)
    connection = psycopg.connect(settings.database_url)
    redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    return build_app(
        settings,
        connection=connection,
        llm_client=httpx.Client(base_url=settings.llm_base_url),
        embeddings_client=httpx.Client(base_url=settings.embeddings_base_url),
        # Durable, multi-replica-safe stores.
        session_store=RedisSessionStore(redis_client),
        outbox_store=PgOutboxStore(ConnectionExecutor(connection)),
    )
