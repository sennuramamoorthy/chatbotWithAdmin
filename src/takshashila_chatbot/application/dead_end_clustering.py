"""Dead-end clustering worker (the batch step of the learning loop, AC-9.1).

Reads unanswered (dead-end) questions, embeds them, groups by similarity, and
persists the frequency-ranked groups for the admin dashboard. A human then turns
the top groups into published knowledge — closing the loop.
"""

from __future__ import annotations

from ..domain.clustering import cluster_questions
from .ports import (
    DeadEndClusterRepository,
    DeadEndGroup,
    DeadEndLogStore,
    Embedder,
)


class DeadEndClusteringService:
    def __init__(
        self,
        log_store: DeadEndLogStore,
        embedder: Embedder,
        cluster_repo: DeadEndClusterRepository,
        *,
        threshold: float = 0.7,
    ) -> None:
        self._log_store = log_store
        self._embedder = embedder
        self._cluster_repo = cluster_repo
        self._threshold = threshold

    def run(self) -> list[DeadEndGroup]:
        questions = self._log_store.dead_end_questions()
        items = [(text, self._embedder.embed(text)) for text in questions]
        clusters = cluster_questions(items, self._threshold)
        groups = [
            DeadEndGroup(representative_text=c.representative_text, frequency=c.frequency)
            for c in clusters
        ]
        self._cluster_repo.replace_all(groups)
        return groups
