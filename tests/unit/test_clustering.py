"""Dead-end clustering core (AC-9.1: group by similarity, rank by frequency)."""

import pytest

from takshashila_chatbot.domain.clustering import cluster_questions, cosine_similarity

pytestmark = pytest.mark.unit


def test_cosine_similarity_identical_is_one():
    assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_is_zero():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_similarity_zero_vector_is_zero():
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_groups_similar_questions_and_ranks_by_frequency():
    items = [
        ("What is the hostel fee?", [1.0, 0.0]),
        ("hostel fees?", [0.99, 0.01]),  # similar -> same group
        ("Where is the library?", [0.0, 1.0]),  # different -> own group
    ]
    clusters = cluster_questions(items, threshold=0.9)

    assert len(clusters) == 2
    assert clusters[0].frequency == 2  # most frequent ranked first
    assert "hostel" in clusters[0].representative_text.lower()
    assert clusters[1].frequency == 1


def test_below_threshold_stays_separate():
    items = [("a", [1.0, 0.0]), ("b", [0.7, 0.7])]  # cosine ~0.707 < 0.9
    assert len(cluster_questions(items, threshold=0.9)) == 2


def test_picks_nearest_among_multiple_clusters():
    items = [
        ("a", [1.0, 0.0, 0.0]),
        ("b", [0.0, 1.0, 0.0]),
        ("c", [0.0, 0.0, 1.0]),
        ("a-again", [0.99, 0.01, 0.0]),  # nearest to 'a'; must compare against b, c too
    ]
    clusters = cluster_questions(items, threshold=0.9)
    assert sorted((c.frequency for c in clusters), reverse=True) == [2, 1, 1]


def test_empty_input_returns_empty():
    assert cluster_questions([], threshold=0.9) == []
