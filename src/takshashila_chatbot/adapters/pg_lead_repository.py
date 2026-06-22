"""Postgres lead repository — implements the ``LeadRepository`` port.

Leads are inserted as ``delivery_status='pending'`` (the dashboard source of truth);
the async email-delivery outbox/retry (EC-18) is a later increment that flips the
status. SQL goes through the injected ``Executor`` so it is testable without a driver.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

from ..application.lead_service import LeadDraft, StoredLead
from .db import Executor

INSERT_SQL = """
INSERT INTO leads
    (name, email, phone, program, message, dead_end_question, created_at, delivery_status)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
RETURNING id
"""

LIST_SQL = """
SELECT id, name, email, phone, program, message, dead_end_question, created_at, delivery_status
FROM leads
ORDER BY created_at DESC
"""

PURGE_SQL = "DELETE FROM leads WHERE created_at < %s RETURNING id"


def _row_to_lead(row: Sequence) -> StoredLead:
    return StoredLead(
        id=str(row[0]),
        name=row[1],
        email=row[2],
        phone=row[3],
        program=row[4],
        message=row[5],
        dead_end_question=row[6],
        created_at=row[7],
        delivery_status=row[8],
    )


class PgLeadRepository:
    def __init__(self, executor: Executor) -> None:
        self._executor = executor

    def save(self, draft: LeadDraft) -> StoredLead:
        rows = self._executor.execute(
            INSERT_SQL,
            (
                draft.name,
                draft.email,
                draft.phone,
                draft.program,
                draft.message,
                draft.dead_end_question,
                draft.created_at,
                "pending",
            ),
        )
        return StoredLead(
            id=str(rows[0][0]),
            name=draft.name,
            email=draft.email,
            phone=draft.phone,
            program=draft.program,
            message=draft.message,
            dead_end_question=draft.dead_end_question,
            created_at=draft.created_at,
            delivery_status="pending",
        )

    def list(self) -> list[StoredLead]:
        return [_row_to_lead(row) for row in self._executor.execute(LIST_SQL)]

    def purge_before(self, cutoff: dt.date) -> int:
        return len(self._executor.execute(PURGE_SQL, (cutoff,)))
