"""FastAPI application factory.

`create_app` takes its collaborators as arguments (no globals), so tests inject
deterministic fakes and production wires real adapters. Endpoints:
  * GET  /api/v1/health  — liveness (widget soft-fail probe)
  * POST /api/v1/chat    — SSE answer stream, rate-limited, soft-failing
  * POST /api/v1/leads   — consented lead capture with field validation
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass

from collections.abc import Sequence

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from ..application.admin_auth import AdminAuth
from ..application.answer_service import AnswerService, Outcome
from ..application.answer_stream import AnswerStreamService
from ..application.content_service import ContentService, Document
from ..application.dashboard import DashboardService
from ..application.dead_end_clustering import DeadEndClusteringService
from ..application.lead_delivery import LeadDeliveryService
from ..application.lead_service import LeadService, StoredLead
from ..application.session import SessionMemory
from ..domain.leads import LeadInput
from ..domain.rate_limit import RateLimiter
from .schemas import ChatRequest, ContentRequest, LeadRequest, LoginRequest


@dataclass(frozen=True)
class StaticContact:
    """Fallback/soft-fail Admissions contact (placeholders — wired at OQ-4)."""

    email: str = "admissions@takshashila.example"
    phone: str = "+91-00000-00000"
    page: str = "https://takshashila.example/admissions"

    def as_dict(self) -> dict[str, str]:
        return {"email": self.email, "phone": self.phone, "page": self.page}


DEFAULT_CONTACT = StaticContact()
SLOW_DOWN_MESSAGE = (
    "You're sending messages very quickly — please wait a moment and try again."
)
SOFT_FAIL_MESSAGE = (
    "Our assistant is temporarily unavailable. Please reach the Admissions team directly."
)


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _chunk(text: str) -> Iterator[str]:
    # Light word-level chunking to exercise the stream; real token-by-token
    # streaming arrives with the self-hosted LLM adapter.
    for word in text.split(" "):
        yield word + " "


def _lead_dict(lead: StoredLead) -> dict:
    return {
        "id": lead.id,
        "name": lead.name,
        "email": lead.email,
        "phone": lead.phone,
        "program": lead.program,
        "message": lead.message,
        "dead_end_question": lead.dead_end_question,
        "created_at": lead.created_at.isoformat(),
        "delivery_status": lead.delivery_status,
    }


def _doc_dict(doc: Document) -> dict:
    return {
        "id": doc.id,
        "topic": doc.topic,
        "title": doc.title,
        "draft_body": doc.draft_body,
        "published_body": doc.published_body,
        "published_version": doc.published_version,
        "last_updated": doc.last_updated.isoformat() if doc.last_updated else None,
        "metadata": dict(doc.metadata),
    }


def create_app(
    *,
    answer_service: AnswerService,
    lead_service: LeadService,
    rate_limiter: RateLimiter,
    contact: StaticContact = DEFAULT_CONTACT,
    dashboard_service: DashboardService | None = None,
    clustering_service: DeadEndClusteringService | None = None,
    content_service: ContentService | None = None,
    answer_stream_service: AnswerStreamService | None = None,
    session_memory: SessionMemory | None = None,
    lead_delivery: LeadDeliveryService | None = None,
    admin_token: str = "",
    admin_auth: AdminAuth | None = None,
    cors_origins: Sequence[str] = ("*",),
) -> FastAPI:
    app = FastAPI(title="Takshashila Chatbot API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/v1/chat")
    def chat(req: ChatRequest):
        decision = rate_limiter.check(req.session_id or "anonymous")
        if not decision.allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "message": SLOW_DOWN_MESSAGE,
                    "retry_after": round(decision.retry_after, 1),
                },
            )

        session_id = req.session_id or "anonymous"
        # Resolve bare follow-ups against session context (FR-9) before retrieval.
        query = (
            session_memory.contextual_query(session_id, req.message)
            if session_memory is not None
            else req.message
        )

        def remember(answer: str) -> None:
            if session_memory is not None:
                session_memory.record(session_id, "user", req.message)
                session_memory.record(session_id, "bot", answer)

        # Preferred path: true token-by-token streaming from the LLM.
        if answer_stream_service is not None:

            def streamed() -> Iterator[str]:
                parts: list[str] = []
                try:
                    for event in answer_stream_service.stream(query):
                        if event.get("type") == "token":
                            parts.append(event["text"])
                        yield _sse(event)
                except Exception:  # noqa: BLE001 — soft-fail in-band once streaming
                    yield _sse({"type": "token", "text": SOFT_FAIL_MESSAGE})
                    yield _sse(
                        {"type": "done", "outcome": "error", "language": None,
                         "citations": [], "offer_lead": False}
                    )
                    return
                remember("".join(parts))

            return StreamingResponse(streamed(), media_type="text/event-stream")

        # Fallback path: non-streaming service, chunked into SSE.
        try:
            result = answer_service.answer(query)
        except Exception:  # noqa: BLE001 — any backend failure must soft-fail, not 500
            return JSONResponse(
                status_code=503,
                content={"message": SOFT_FAIL_MESSAGE, "contact": contact.as_dict()},
            )

        remember(result.text)

        def rendered() -> Iterator[str]:
            pieces = _chunk(result.text) if result.outcome is Outcome.ANSWERED else [result.text]
            for piece in pieces:
                yield _sse({"type": "token", "text": piece})
            yield _sse(
                {
                    "type": "done",
                    "outcome": result.outcome.value,
                    "language": result.language,
                    "citations": list(result.citations),
                    "offer_lead": result.offer_lead,
                }
            )

        return StreamingResponse(rendered(), media_type="text/event-stream")

    @app.post("/api/v1/leads")
    def create_lead(req: LeadRequest):
        data = LeadInput(
            name=req.name,
            email=req.email,
            phone=req.phone,
            program=req.program,
            message=req.message,
            consent=req.consent,
        )
        result = lead_service.submit(data, dead_end_question=req.dead_end_question)
        if not result.ok:
            return JSONResponse(
                status_code=422,
                content={
                    "errors": [
                        {"field": e.field, "code": e.code, "message": e.message}
                        for e in result.errors
                    ]
                },
            )
        # Persisted (source of truth) — now queue the Admissions email for async,
        # retried delivery so a consented lead is never lost (EC-18).
        if lead_delivery is not None:
            lead_delivery.enqueue(
                to=contact.email,
                subject=f"New admissions lead: {data.name}",
                body=(
                    f"Lead {result.lead_id}\nName: {data.name}\nEmail: {data.email}\n"
                    f"Phone: {data.phone}\nProgram: {data.program}\n"
                    f"Dead-end question: {req.dead_end_question}\nMessage: {data.message}"
                ),
            )
        return JSONResponse(status_code=201, content={"lead_id": result.lead_id})

    if dashboard_service is not None:
        # Default to a legacy service-token-only auth so existing single-token wiring
        # keeps working; richer wirings pass an AdminAuth with username/password login.
        auth = admin_auth or AdminAuth(service_token=admin_token)
        _register_admin_routes(
            app, dashboard_service, clustering_service, content_service, auth
        )

    return app


def _register_admin_routes(
    app: FastAPI,
    dashboard: DashboardService,
    clustering: DeadEndClusteringService | None,
    content: ContentService | None,
    auth: AdminAuth,
) -> None:
    def require_admin(authorization: str | None = Header(default=None)) -> None:
        # Single admin role (A-1); accepts a service token or a login session token.
        if not auth.authorize(authorization):
            raise HTTPException(status_code=401, detail="unauthorized")

    guard = Depends(require_admin)

    @app.post("/api/v1/admin/login")
    def login(req: LoginRequest):
        token = auth.login(req.username, req.password)
        if token is None:
            raise HTTPException(status_code=401, detail="invalid credentials")
        return {"token": token, "username": req.username, "expires_in": auth.ttl_seconds}

    @app.get("/api/v1/admin/dashboard/dead-ends", dependencies=[guard])
    def dead_ends():
        return {
            "dead_ends": [
                {"question": g.representative_text, "frequency": g.frequency}
                for g in dashboard.dead_ends()
            ]
        }

    @app.get("/api/v1/admin/dashboard/stats", dependencies=[guard])
    def stats():
        s = dashboard.stats()
        return {
            "questions_per_day": s.questions_per_day,
            "busiest_topics": [list(t) for t in s.busiest_topics],
            "lead_count": s.lead_count,
            "answered_count": s.answered_count,
            "dead_end_count": s.dead_end_count,
        }

    @app.get("/api/v1/admin/leads", dependencies=[guard])
    def leads():
        return {"leads": [_lead_dict(lead) for lead in dashboard.leads()]}

    @app.post("/api/v1/admin/cluster", dependencies=[guard])
    def cluster():
        if clustering is None:
            raise HTTPException(status_code=503, detail="clustering unavailable")
        return {"clustered": len(clustering.run())}

    if content is None:
        return

    @app.get("/api/v1/admin/content/{doc_id}", dependencies=[guard])
    def get_content(doc_id: str):
        doc = content.get(doc_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="not found")
        return _doc_dict(doc)

    @app.put("/api/v1/admin/content/{doc_id}", dependencies=[guard])
    def save_content(doc_id: str, req: ContentRequest):
        doc = content.save_draft(
            doc_id, topic=req.topic, title=req.title, body=req.body, metadata=req.metadata
        )
        return _doc_dict(doc)

    @app.post("/api/v1/admin/content/{doc_id}/publish", dependencies=[guard])
    def publish_content(doc_id: str):
        try:
            doc = content.publish(doc_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="not found") from None
        return _doc_dict(doc)
