"""DeadEndClusteringService — embeds dead-ends, clusters, persists ranked groups."""

import datetime as dt

import pytest

from takshashila_chatbot.application.dead_end_clustering import DeadEndClusteringService
from takshashila_chatbot.application.ports import QuestionOutcome
from takshashila_chatbot.application.repositories import (
    InMemoryDeadEndClusterRepository,
    InMemoryQuestionLog,
)
from takshashila_chatbot.domain.clock import IST, FixedClock
from takshashila_chatbot.testing.fakes import ScriptedEmbedder

pytestmark = pytest.mark.integration


def test_clusters_dead_ends_and_persists_ranked():
    clock = FixedClock(dt.datetime(2026, 6, 16, 12, 0, tzinfo=IST))
    log = InMemoryQuestionLog(clock)
    log.record(QuestionOutcome("What is the hostel fee?", "dead_end", "fees", "en"))
    log.record(QuestionOutcome("hostel fees?", "dead_end", "fees", "en"))
    log.record(QuestionOutcome("Where is the library?", "dead_end", "facilities", "en"))
    log.record(QuestionOutcome("What is the CSE fee?", "answered", "fees", "en"))  # ignored

    embedder = ScriptedEmbedder(
        {
            "What is the hostel fee?": [1.0, 0.0],
            "hostel fees?": [0.99, 0.01],
            "Where is the library?": [0.0, 1.0],
        }
    )
    repo = InMemoryDeadEndClusterRepository()
    service = DeadEndClusteringService(log, embedder, repo, threshold=0.9)

    groups = service.run()

    assert [g.frequency for g in groups] == [2, 1]
    assert "hostel" in groups[0].representative_text.lower()
    assert repo.ranked()[0].frequency == 2  # persisted
    assert "What is the CSE fee?" not in embedder.seen  # answered question never embedded
