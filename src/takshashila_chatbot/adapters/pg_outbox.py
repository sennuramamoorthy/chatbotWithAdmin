"""Postgres outbox store — implements the ``OutboxStore`` port (US-7 / EC-18).

The lead-email outbox is the durable, retryable handoff between persisting a
consented lead and actually delivering its notification email. Persisting here
means a lead is NEVER lost when email fails: a row stays ``pending``/``failed``
(retry-eligible) until it is finally ``sent``. SQL goes through the injected
``Executor`` so it is testable without a driver, mirroring ``PgLeadRepository``.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..application.lead_delivery import OutboxRecord
from .db import Executor

OUTBOX_SCHEMA: str = """
CREATE TABLE IF NOT EXISTS outbox (
    id BIGSERIAL PRIMARY KEY,
    recipient TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INT NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

INSERT_SQL = """
INSERT INTO outbox (recipient, subject, body)
VALUES (%s, %s, %s)
RETURNING id
"""

PENDING_SQL = """
SELECT id, recipient, subject, body, status, attempts, last_error
FROM outbox
WHERE status IN ('pending', 'failed')
ORDER BY id
"""

MARK_SENT_SQL = "UPDATE outbox SET status = 'sent' WHERE id = %s"

MARK_FAILED_SQL = """
UPDATE outbox
SET status = 'failed', attempts = attempts + 1, last_error = %s
WHERE id = %s
"""


def _row_to_record(row: Sequence) -> OutboxRecord:
    return OutboxRecord(
        id=str(row[0]),
        to=row[1],
        subject=row[2],
        body=row[3],
        status=row[4],
        attempts=row[5],
        last_error=row[6],
    )


class PgOutboxStore:
    def __init__(self, executor: Executor) -> None:
        self._executor = executor

    def add(self, to: str, subject: str, body: str) -> OutboxRecord:
        rows = self._executor.execute(INSERT_SQL, (to, subject, body))
        return OutboxRecord(
            id=str(rows[0][0]),
            to=to,
            subject=subject,
            body=body,
            status="pending",
            attempts=0,
            last_error=None,
        )

    def pending(self) -> list[OutboxRecord]:
        # "failed" stays eligible so deliver_pending retries it (EC-18).
        return [_row_to_record(row) for row in self._executor.execute(PENDING_SQL)]

    def mark_sent(self, id: str) -> None:
        self._executor.execute(MARK_SENT_SQL, (id,))

    def mark_failed(self, id: str, error: str) -> None:
        self._executor.execute(MARK_FAILED_SQL, (error, id))
