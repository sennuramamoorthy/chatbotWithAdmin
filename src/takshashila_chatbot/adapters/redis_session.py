"""Redis-backed session memory — implements the ``SessionStore`` port (US-6 / FR-9).

A durable replacement for ``InMemorySessionStore`` that works across replicas and
survives restarts. Memory stays short-lived and identity-free: each session is a
single Redis key holding its recent turns as JSON, capped to ``max_turns`` and
expired by a sliding TTL (Redis handles expiry, so a missing/expired key simply
reads as an empty history). Depends only on a tiny ``RedisClient`` protocol, so
the real redis-py client (``decode_responses=True``) drops in without importing it.
"""

from __future__ import annotations

import json
from typing import Protocol

from ..application.session import Turn


class RedisClient(Protocol):
    """The slice of redis-py this store needs (decode_responses=True client)."""

    def get(self, key: str) -> str | None: ...

    def set(self, key: str, value: str, ex: int) -> None: ...


class RedisSessionStore:
    """Ephemeral per-session memory backed by Redis (FR-9).

    Keyed only by an opaque ``session_id``. Each ``append`` refreshes the TTL
    (sliding expiry) and trims to the most recent ``max_turns`` turns.
    """

    def __init__(
        self,
        client: RedisClient,
        *,
        ttl_seconds: int = 1800,
        max_turns: int = 10,
    ) -> None:
        self._client = client
        self._ttl_seconds = ttl_seconds
        self._max_turns = max_turns

    def _key(self, session_id: str) -> str:
        return f"session:{session_id}"

    def load(self, session_id: str) -> list[Turn]:
        raw = self._client.get(self._key(session_id))
        if raw is None:  # missing or expired key -> empty history
            return []
        return [Turn(role=item["role"], text=item["text"]) for item in json.loads(raw)]

    def append(self, session_id: str, turn: Turn) -> None:
        turns = self.load(session_id)
        turns.append(turn)
        turns = turns[-self._max_turns :]
        payload = json.dumps([{"role": t.role, "text": t.text} for t in turns])
        self._client.set(self._key(session_id), payload, ex=self._ttl_seconds)
