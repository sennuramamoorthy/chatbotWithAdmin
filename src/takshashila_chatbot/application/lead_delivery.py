"""Lead-delivery outbox (US-7 / FR-13 / EC-18).

A consented lead is persisted by ``LeadService`` first; email delivery is a
separate, *retryable* step so a lead is NEVER lost when email fails (EC-18). The
outbox is the transactional handoff: ``enqueue`` records a "pending" message,
``deliver_pending`` attempts each one and marks it "sent" or "failed". A "failed"
message stays pending-eligible, so the next ``deliver_pending`` retries it
(TC-026) — failures are recorded with an error and attempt count, never dropped.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class EmailSender(Protocol):
    """Sends one message. Raises on failure (the outbox catches and records it)."""

    def send(self, to: str, subject: str, body: str) -> None: ...


@dataclass(frozen=True)
class OutboxRecord:
    id: str
    to: str
    subject: str
    body: str
    status: str  # "pending" | "sent" | "failed"
    attempts: int
    last_error: str | None


class OutboxStore(Protocol):
    def add(self, to: str, subject: str, body: str) -> OutboxRecord: ...

    def pending(self) -> list[OutboxRecord]: ...

    def mark_sent(self, id: str) -> None: ...

    def mark_failed(self, id: str, error: str) -> None: ...


class InMemoryOutboxStore:
    """Volatile but real outbox; the DB adapter implements the same interface."""

    def __init__(self) -> None:
        self._records: dict[str, OutboxRecord] = {}
        self._seq = 0

    def add(self, to: str, subject: str, body: str) -> OutboxRecord:
        self._seq += 1
        record = OutboxRecord(
            id=f"msg-{self._seq}",  # deterministic; DB uses a sequence/uuid
            to=to,
            subject=subject,
            body=body,
            status="pending",
            attempts=0,
            last_error=None,
        )
        self._records[record.id] = record
        return record

    def pending(self) -> list[OutboxRecord]:
        # "failed" stays eligible so deliver_pending retries it (EC-18).
        return [
            r for r in self._records.values() if r.status in ("pending", "failed")
        ]

    def mark_sent(self, id: str) -> None:
        record = self._records[id]
        self._records[id] = OutboxRecord(
            id=record.id,
            to=record.to,
            subject=record.subject,
            body=record.body,
            status="sent",
            attempts=record.attempts + 1,
            last_error=None,
        )

    def mark_failed(self, id: str, error: str) -> None:
        record = self._records[id]
        self._records[id] = OutboxRecord(
            id=record.id,
            to=record.to,
            subject=record.subject,
            body=record.body,
            status="failed",
            attempts=record.attempts + 1,
            last_error=error,
        )


class LeadDeliveryService:
    def __init__(self, store: OutboxStore, sender: EmailSender) -> None:
        self._store = store
        self._sender = sender

    def enqueue(self, to: str, subject: str, body: str) -> str:
        return self._store.add(to, subject, body).id

    def deliver_pending(self) -> tuple[int, int]:
        sent_count = 0
        failed_count = 0
        for record in self._store.pending():
            try:
                self._sender.send(record.to, record.subject, record.body)
            except Exception as exc:  # never lose a lead — record and retry later
                self._store.mark_failed(record.id, str(exc))
                failed_count += 1
            else:
                self._store.mark_sent(record.id)
                sent_count += 1
        return sent_count, failed_count
