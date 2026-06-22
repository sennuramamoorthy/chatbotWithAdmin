"""HashingEmbedder — the deterministic demo embedder (drives learning-loop clustering
in `make run`). Production uses the real HttpEmbedder; this only needs to give distinct
questions distinct vectors and keep near-duplicates close under cosine similarity."""

import pytest

from takshashila_chatbot.domain.clustering import cosine_similarity
from takshashila_chatbot.testing.fakes import HashingEmbedder

pytestmark = pytest.mark.unit


def test_near_duplicate_questions_are_more_similar_than_unrelated_ones():
    embedder = HashingEmbedder()
    weather_a = embedder.embed("What is the weather today?")
    weather_b = embedder.embed("What is the weather forecast?")  # shares "weather"
    movie = embedder.embed("recommend a good movie to watch")  # no shared content word

    assert cosine_similarity(weather_a, weather_b) > cosine_similarity(weather_a, movie)


def test_is_deterministic_across_instances():
    # Stable hashing (not salted `hash`) so clustering is reproducible across processes.
    assert HashingEmbedder().embed("hostel fee") == HashingEmbedder().embed("hostel fee")


def test_text_with_no_content_words_yields_a_zero_vector():
    embedder = HashingEmbedder(dim=8)
    assert embedder.embed("what is the") == [0.0] * 8  # all stopwords -> nothing to hash
    assert embedder.embed("") == [0.0] * 8  # empty -> no tokens
