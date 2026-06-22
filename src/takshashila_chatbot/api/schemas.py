"""Request schemas.

Lead fields are intentionally lenient (defaults instead of required) so that
validation flows through the domain rules in ``validate_lead`` and returns our
structured field errors (matching the TC error codes) rather than FastAPI's
generic 422 shape.
"""

from __future__ import annotations

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    page_url: str | None = None


class LeadRequest(BaseModel):
    name: str = ""
    email: str | None = None
    phone: str | None = None
    program: str | None = None
    message: str | None = None
    consent: bool = False
    dead_end_question: str | None = None
    session_id: str | None = None


class ContentRequest(BaseModel):
    topic: str
    title: str
    body: str
    metadata: dict[str, str] = {}


class LoginRequest(BaseModel):
    username: str = ""
    password: str = ""
