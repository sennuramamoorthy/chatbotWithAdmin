"""Dead-end clustering core (AC-9.1).

Greedy nearest-centroid grouping of dead-end questions by embedding similarity,
returned ranked by frequency — turning many raw misses into a short, prioritized
knowledge-gap backlog for the admin. Pure: embeddings are supplied by the caller.

This batch-recomputes over the dead-end set, which is ample for v1 scale; an
incremental/online variant is a future optimization.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class QuestionCluster:
    representative_text: str
    frequency: int
    members: tuple[str, ...]


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def cluster_questions(
    items: Sequence[tuple[str, Sequence[float]]], threshold: float
) -> list[QuestionCluster]:
    """Group ``(text, embedding)`` items; return clusters ranked by frequency desc."""
    centroids: list[list[float]] = []
    sums: list[list[float]] = []
    members: list[list[str]] = []

    for text, embedding in items:
        best_index, best_sim = None, -1.0
        for index, centroid in enumerate(centroids):
            sim = cosine_similarity(embedding, centroid)
            if sim > best_sim:
                best_index, best_sim = index, sim

        if best_index is not None and best_sim >= threshold:
            sums[best_index] = [s + e for s, e in zip(sums[best_index], embedding)]
            members[best_index].append(text)
            count = len(members[best_index])
            centroids[best_index] = [s / count for s in sums[best_index]]
        else:
            centroids.append(list(embedding))
            sums.append(list(embedding))
            members.append([text])

    clusters = [
        QuestionCluster(
            representative_text=group[0], frequency=len(group), members=tuple(group)
        )
        for group in members
    ]
    clusters.sort(key=lambda c: c.frequency, reverse=True)  # stable: ties keep order
    return clusters
