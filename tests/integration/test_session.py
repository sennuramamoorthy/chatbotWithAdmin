"""Ephemeral session memory + follow-up rewriting (US-6 / TC-015, TC-016, TC-017)."""

import datetime as dt

import pytest

from takshashila_chatbot.application.session import (
    InMemorySessionStore,
    SessionMemory,
    Turn,
    build_followup_query,
)
from takshashila_chatbot.domain.clock import IST, FixedClock

pytestmark = pytest.mark.integration


def _memory(clock: FixedClock, **kwargs) -> SessionMemory:
    return SessionMemory(InMemorySessionStore(clock, **kwargs))


def test_tc015_followup_carries_prior_subject():
    clock = FixedClock(dt.datetime(2026, 6, 16, 12, 0, tzinfo=IST))
    memory = _memory(clock)
    memory.record("s", "user", "What is the B.Tech CSE fee?")

    rewritten = memory.contextual_query("s", "and the M.Tech?")

    assert isinstance(rewritten, str)
    assert "B.Tech" in rewritten


def test_non_followup_returned_unchanged():
    clock = FixedClock(dt.datetime(2026, 6, 16, 12, 0, tzinfo=IST))
    memory = _memory(clock)
    memory.record("s", "user", "What is the B.Tech CSE fee?")

    assert memory.contextual_query("s", "Where is the library?") == "Where is the library?"


def test_followup_with_empty_history_unchanged():
    assert build_followup_query([], "and the M.Tech?") == "and the M.Tech?"


def test_followup_with_only_bot_turns_unchanged():
    # A follow-up prefix but no *prior user* turn -> last_user_text is None.
    history = [Turn("bot", "Here is some info.")]
    assert build_followup_query(history, "what about hostels?") == "what about hostels?"


def test_build_followup_query_recognises_all_prefixes():
    history = [Turn("user", "B.Tech fee?")]
    for message in ("and X", "and the X", "what about X", "how about X", "also X"):
        assert build_followup_query(history, message) == f"B.Tech fee? {message}"


def test_followup_prefix_match_is_case_insensitive_and_stripped():
    history = [Turn("user", "B.Tech fee?")]
    assert build_followup_query(history, "  AND the M.Tech?") == "B.Tech fee?   AND the M.Tech?"


def test_uses_most_recent_user_turn_skipping_bot():
    history = [
        Turn("user", "B.Tech fee?"),
        Turn("bot", "It is X."),
        Turn("user", "M.Tech fee?"),
        Turn("bot", "It is Y."),
    ]
    assert build_followup_query(history, "and hostels?") == "M.Tech fee? and hostels?"


def test_tc016_append_then_load_persists_across_calls():
    clock = FixedClock(dt.datetime(2026, 6, 16, 12, 0, tzinfo=IST))
    store = InMemorySessionStore(clock)
    store.append("s", Turn("user", "first"))
    store.append("s", Turn("bot", "second"))

    assert store.load("s") == [Turn("user", "first"), Turn("bot", "second")]


def test_load_unknown_session_is_empty():
    clock = FixedClock(dt.datetime(2026, 6, 16, 12, 0, tzinfo=IST))
    store = InMemorySessionStore(clock)
    assert store.load("never-seen") == []


def test_tc016_trims_to_max_turns():
    clock = FixedClock(dt.datetime(2026, 6, 16, 12, 0, tzinfo=IST))
    store = InMemorySessionStore(clock, max_turns=3)
    for i in range(5):
        store.append("s", Turn("user", f"q{i}"))

    turns = store.load("s")
    assert [t.text for t in turns] == ["q2", "q3", "q4"]


def test_tc017_expired_session_discards_context():
    clock = FixedClock(dt.datetime(2026, 6, 16, 12, 0, tzinfo=IST))
    store = InMemorySessionStore(clock, ttl_seconds=1800)
    store.append("s", Turn("user", "What is the B.Tech CSE fee?"))

    clock.advance(1801)  # beyond TTL

    assert store.load("s") == []


def test_tc017_append_after_expiry_starts_fresh():
    clock = FixedClock(dt.datetime(2026, 6, 16, 12, 0, tzinfo=IST))
    store = InMemorySessionStore(clock, ttl_seconds=1800)
    store.append("s", Turn("user", "old subject"))

    clock.advance(1801)  # beyond TTL -> stale
    store.append("s", Turn("user", "new subject"))

    assert store.load("s") == [Turn("user", "new subject")]


def test_within_ttl_session_is_retained():
    clock = FixedClock(dt.datetime(2026, 6, 16, 12, 0, tzinfo=IST))
    store = InMemorySessionStore(clock, ttl_seconds=1800)
    store.append("s", Turn("user", "kept"))

    clock.advance(1800)  # exactly at TTL, not beyond -> still alive
    store.append("s", Turn("bot", "answer"))

    assert store.load("s") == [Turn("user", "kept"), Turn("bot", "answer")]
