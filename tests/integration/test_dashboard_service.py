"""DashboardService — ranked dead-ends, volume stats, and the leads list (AC-9.2)."""

import datetime as dt

import pytest

from takshashila_chatbot.application.dashboard import DashboardService
from takshashila_chatbot.application.lead_service import LeadDraft
from takshashila_chatbot.application.ports import DeadEndGroup, QuestionOutcome
from takshashila_chatbot.application.repositories import (
    InMemoryDeadEndClusterRepository,
    InMemoryLeadRepository,
    InMemoryQuestionLog,
)
from takshashila_chatbot.domain.clock import IST, FixedClock

pytestmark = pytest.mark.integration


def test_dashboard_aggregates_dead_ends_stats_and_leads():
    clock = FixedClock(dt.datetime(2026, 6, 16, 12, 0, tzinfo=IST))

    log = InMemoryQuestionLog(clock)
    log.record(QuestionOutcome("q1", "answered", "fees", "en"))
    log.record(QuestionOutcome("q2", "dead_end", "facilities", "en"))

    clusters = InMemoryDeadEndClusterRepository()
    clusters.replace_all([DeadEndGroup("hostel fee?", 5), DeadEndGroup("bus route?", 2)])

    leads = InMemoryLeadRepository()
    leads.save(LeadDraft("Asha", "a@b.co", None, None, None, None, clock.now()))

    service = DashboardService(clusters, log, leads)

    assert [g.frequency for g in service.dead_ends()] == [5, 2]

    stats = service.stats()
    assert stats.questions_per_day["2026-06-16"] == 2
    assert ("fees", 1) in stats.busiest_topics
    assert stats.lead_count == 1
    assert stats.answered_count == 1  # one answered turn
    assert stats.dead_end_count == 1  # one dead-end turn

    assert len(service.leads()) == 1
