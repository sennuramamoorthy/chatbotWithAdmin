"""ContentService — edit stays a draft until Publish re-indexes it (US-8).

Covers TC-030 (edit without publish hidden), TC-031 (publish live + timestamp),
EC-22/EC-23/TC-040 (only the published state is served).
"""

import datetime as dt

import pytest

from takshashila_chatbot.application.content_service import ContentService
from takshashila_chatbot.application.repositories import (
    InMemoryChunkStore,
    InMemoryContentRepository,
)
from takshashila_chatbot.domain.clock import IST, FixedClock
from takshashila_chatbot.testing.fakes import FakeEmbedder

pytestmark = pytest.mark.integration


def _service(clock=None):
    clock = clock or FixedClock(dt.datetime(2026, 6, 16, 12, 0, tzinfo=IST))
    repo = InMemoryContentRepository()
    chunks = InMemoryChunkStore()
    return ContentService(repo, chunks, FakeEmbedder(), clock), chunks


def test_save_draft_is_not_live():  # TC-030 / EC-22
    service, chunks = _service()
    doc = service.save_draft("hostel", topic="fees", title="Hostel", body="Hostel fee is INR 50,000.")
    assert doc.published_body is None
    assert doc.last_updated is None
    assert chunks.retrieve("hostel fee") == []  # nothing indexed yet


def test_publish_indexes_content_and_stamps_timestamp():  # TC-031 / AC-8.2/8.3
    clock = FixedClock(dt.datetime(2026, 6, 16, 12, 0, tzinfo=IST))
    service, chunks = _service(clock)
    service.save_draft("hostel", topic="fees", title="Hostel", body="Hostel fee is INR 50,000 per year.")

    published = service.publish("hostel")

    assert published.published_body == "Hostel fee is INR 50,000 per year."
    assert published.published_version == 1
    assert published.last_updated == clock.now()

    hits = chunks.retrieve("hostel fee")
    assert hits and "50,000" in hits[0].text  # now retrievable


def test_edits_are_hidden_until_republish():  # EC-22 / EC-23 / TC-040
    service, chunks = _service()
    service.save_draft("d", topic="facilities", title="Library", body="Library opens at 8 AM.")
    service.publish("d")

    service.save_draft("d", topic="facilities", title="Library", body="Library opens at 6 AM.")  # edit only
    assert service.get("d").published_body == "Library opens at 8 AM."  # last published served
    assert "8 AM" in chunks.retrieve("library")[0].text

    service.publish("d")  # now it goes live
    assert "6 AM" in chunks.retrieve("library")[0].text
    assert service.get("d").published_version == 2


def test_publish_unknown_document_raises():
    service, _ = _service()
    with pytest.raises(KeyError):
        service.publish("missing")
