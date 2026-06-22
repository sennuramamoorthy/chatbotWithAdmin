"""Ephemeral session memory + follow-up query rewriting (US-6 / FR-9).

Session memory is short-lived and *never tied to identity*: it exists only to
let a bare follow-up like "and the M.Tech?" carry the prior subject into
retrieval. Memory is per-session, capped, and expires after a TTL so stale
context is discarded (the next turn starts fresh).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ..domain.clock import Clock

_FOLLOWUP_PREFIXES = ("and ", "and the", "what about", "how about", "also ")


@dataclass(frozen=True)
class Turn:
    """A single utterance in a conversation."""

    role: str  # "user" | "bot"
    text: str


@runtime_checkable
class SessionStore(Protocol):
    """Stores the recent turns of a session."""

    def load(self, session_id: str) -> list[Turn]:
        ...

    def append(self, session_id: str, turn: Turn) -> None:
        ...


class InMemorySessionStore:
    """Ephemeral per-session memory (FR-9).

    Volatile and identity-free: keyed only by an opaque ``session_id``. A
    session expires when more than ``ttl_seconds`` elapse since its last turn;
    an expired session is treated as empty and reset on the next ``append``.
    Only the most recent ``max_turns`` turns are retained.
    """

    def __init__(self, clock: Clock, *, ttl_seconds: int = 1800, max_turns: int = 10) -> None:
        self._clock = clock
        self._ttl_seconds = ttl_seconds
        self._max_turns = max_turns
        self._turns: dict[str, list[Turn]] = {}
        self._last_at: dict[str, dt.datetime] = {}

    def _expired(self, session_id: str) -> bool:
        last_at = self._last_at.get(session_id)
        if last_at is None:
            return False
        return (self._clock.now() - last_at).total_seconds() > self._ttl_seconds

    def load(self, session_id: str) -> list[Turn]:
        if self._expired(session_id):
            return []
        return list(self._turns.get(session_id, []))

    def append(self, session_id: str, turn: Turn) -> None:
        if self._expired(session_id):
            self._turns[session_id] = []
        turns = self._turns.setdefault(session_id, [])
        turns.append(turn)
        del turns[: -self._max_turns]
        self._last_at[session_id] = self._clock.now()


def build_followup_query(history: list[Turn], message: str) -> str:
    """Carry the prior subject into a bare follow-up (pure).

    If ``message`` looks like a follow-up (e.g. "and the M.Tech?") and there is
    a prior user turn, prepend that turn's text so retrieval keeps the subject.
    Otherwise the message is returned unchanged.
    """
    normalized = message.strip().lower()
    if not normalized.startswith(_FOLLOWUP_PREFIXES):
        return message
    last_user_text = next(
        (turn.text for turn in reversed(history) if turn.role == "user"), None
    )
    if last_user_text is None:
        return message
    return f"{last_user_text} {message}"


class SessionMemory:
    """Application-facing facade over a :class:`SessionStore`."""

    def __init__(self, store: SessionStore) -> None:
        self._store = store

    def contextual_query(self, session_id: str, message: str) -> str:
        return build_followup_query(self._store.load(session_id), message)

    def record(self, session_id: str, role: str, text: str) -> None:
        self._store.append(session_id, Turn(role, text))
