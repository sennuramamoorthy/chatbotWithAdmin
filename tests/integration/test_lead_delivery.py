"""Lead-delivery outbox — enqueue, deliver, and retry-never-lose (US-7/EC-18/TC-026)."""

import pytest

from takshashila_chatbot.adapters.log_email_sender import LogEmailSender
from takshashila_chatbot.application.lead_delivery import (
    InMemoryOutboxStore,
    LeadDeliveryService,
)

pytestmark = pytest.mark.integration


class WorkingSender:
    """Records every message it accepts and never raises."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def send(self, to: str, subject: str, body: str) -> None:
        self.sent.append((to, subject, body))


class FailingSender:
    def send(self, to: str, subject: str, body: str) -> None:
        raise RuntimeError("smtp down")


def test_enqueue_creates_one_pending_record():
    store = InMemoryOutboxStore()
    service = LeadDeliveryService(store, WorkingSender())

    msg_id = service.enqueue("admissions@x.edu", "New lead", "Asha wants CSE")

    pending = store.pending()
    assert msg_id == "msg-1"
    assert len(pending) == 1
    record = pending[0]
    assert record.status == "pending"
    assert record.attempts == 0
    assert record.last_error is None
    assert (record.to, record.subject, record.body) == (
        "admissions@x.edu",
        "New lead",
        "Asha wants CSE",
    )


def test_deliver_pending_marks_sent_and_clears_from_pending():
    store = InMemoryOutboxStore()
    sender = WorkingSender()
    service = LeadDeliveryService(store, sender)
    service.enqueue("admissions@x.edu", "New lead", "Asha wants CSE")

    result = service.deliver_pending()

    assert result == (1, 0)
    assert sender.sent == [("admissions@x.edu", "New lead", "Asha wants CSE")]
    assert store.pending() == []  # sent records drop out of the pending set


def test_failed_delivery_is_recorded_then_retried_and_not_lost():
    # EC-18 / TC-026: email fails first, lead survives, second run delivers it.
    store = InMemoryOutboxStore()
    service = LeadDeliveryService(store, FailingSender())
    service.enqueue("admissions@x.edu", "New lead", "Asha wants CSE")

    first = service.deliver_pending()

    assert first == (0, 1)
    still_pending = store.pending()
    assert len(still_pending) == 1  # retryable — never silently lost
    failed = still_pending[0]
    assert failed.status == "failed"
    assert failed.attempts == 1
    assert failed.last_error == "smtp down"

    # Retry with a now-working sender: the same lead is delivered, not dropped.
    working = WorkingSender()
    retry = LeadDeliveryService(store, working).deliver_pending()

    assert retry == (1, 0)
    assert working.sent == [("admissions@x.edu", "New lead", "Asha wants CSE")]
    assert store.pending() == []


def test_log_email_sender_does_not_raise():
    LogEmailSender().send("admissions@x.edu", "New lead", "Asha wants CSE")
