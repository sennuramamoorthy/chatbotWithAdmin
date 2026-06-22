"""RedisSessionStore — round-trips Turns, trims to max_turns, sliding TTL.

Driver-free: exercised through a dict-backed fake RedisClient so we can assert
JSON round-tripping, trimming, key isolation, and the TTL passed to ``set``.
"""

import json

import pytest

from takshashila_chatbot.adapters.redis_session import RedisSessionStore
from takshashila_chatbot.application.session import SessionStore, Turn

pytestmark = pytest.mark.integration


class FakeRedis:
    """In-memory dict-backed RedisClient; records the ``ex`` passed to set()."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ex_calls: list[int] = []

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def set(self, key: str, value: str, ex: int) -> None:
        self.store[key] = value
        self.ex_calls.append(ex)


def test_store_satisfies_session_store_protocol():
    store: SessionStore = RedisSessionStore(FakeRedis())
    assert isinstance(store, SessionStore)


def test_load_missing_key_returns_empty():
    store = RedisSessionStore(FakeRedis())
    assert store.load("nope") == []


def test_append_then_load_round_trips_turns():
    store = RedisSessionStore(FakeRedis())

    store.append("s1", Turn(role="user", text="B.Tech fees?"))
    store.append("s1", Turn(role="bot", text="It is 1L."))

    assert store.load("s1") == [
        Turn(role="user", text="B.Tech fees?"),
        Turn(role="bot", text="It is 1L."),
    ]


def test_append_uses_expected_key_and_json_shape():
    redis = FakeRedis()
    store = RedisSessionStore(redis)

    store.append("abc", Turn(role="user", text="hi"))

    assert "session:abc" in redis.store
    assert json.loads(redis.store["session:abc"]) == [{"role": "user", "text": "hi"}]


def test_append_trims_to_max_turns():
    redis = FakeRedis()
    store = RedisSessionStore(redis, max_turns=3)

    for i in range(5):
        store.append("s1", Turn(role="user", text=f"m{i}"))

    loaded = store.load("s1")
    assert [t.text for t in loaded] == ["m2", "m3", "m4"]


def test_append_sets_sliding_ttl():
    redis = FakeRedis()
    store = RedisSessionStore(redis, ttl_seconds=900)

    store.append("s1", Turn(role="user", text="a"))
    store.append("s1", Turn(role="bot", text="b"))

    # Every append refreshes the TTL (sliding expiry).
    assert redis.ex_calls == [900, 900]


def test_sessions_are_independent():
    store = RedisSessionStore(FakeRedis())

    store.append("s1", Turn(role="user", text="one"))
    store.append("s2", Turn(role="user", text="two"))

    assert store.load("s1") == [Turn(role="user", text="one")]
    assert store.load("s2") == [Turn(role="user", text="two")]
