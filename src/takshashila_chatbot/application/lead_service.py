"""Lead submission (FR-11, FR-12, FR-13).

Validates with the domain rules, then persists a stamped lead via a repository.
Persistence is the source of truth; async email delivery (outbox/retry, EC-18) is
a later increment — leads are created with ``delivery_status="pending"``.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Protocol

from ..domain.clock import Clock
from ..domain.leads import FieldError, LeadInput, validate_lead


@dataclass(frozen=True)
class LeadDraft:
    name: str
    email: str | None
    phone: str | None
    program: str | None
    message: str | None
    dead_end_question: str | None
    created_at: dt.datetime


@dataclass(frozen=True)
class StoredLead:
    id: str
    name: str
    email: str | None
    phone: str | None
    program: str | None
    message: str | None
    dead_end_question: str | None
    created_at: dt.datetime
    delivery_status: str = "pending"


class LeadRepository(Protocol):
    def save(self, draft: LeadDraft) -> StoredLead: ...

    def list(self) -> list[StoredLead]: ...


@dataclass(frozen=True)
class SubmitResult:
    ok: bool
    lead_id: str | None = None
    errors: tuple[FieldError, ...] = ()


class LeadService:
    def __init__(self, repo: LeadRepository, clock: Clock) -> None:
        self._repo = repo
        self._clock = clock

    def submit(
        self, data: LeadInput, *, dead_end_question: str | None = None
    ) -> SubmitResult:
        errors = validate_lead(data)
        if errors:
            return SubmitResult(ok=False, errors=tuple(errors))

        draft = LeadDraft(
            name=data.name.strip(),
            email=data.email.strip() if data.email else None,
            phone=data.phone.strip() if data.phone else None,
            program=data.program,
            message=data.message,
            dead_end_question=dead_end_question,
            created_at=self._clock.now(),
        )
        stored = self._repo.save(draft)
        return SubmitResult(ok=True, lead_id=stored.id)
