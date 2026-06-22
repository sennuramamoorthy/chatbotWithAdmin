"""Admin dashboard read model (US-9, FR-17, AC-9.1/9.2)."""

from __future__ import annotations

from dataclasses import replace

from .lead_service import LeadRepository, StoredLead
from .ports import (
    DeadEndClusterRepository,
    DeadEndGroup,
    StatsStore,
    VolumeStats,
)


class DashboardService:
    def __init__(
        self,
        cluster_repo: DeadEndClusterRepository,
        stats_store: StatsStore,
        lead_repo: LeadRepository,
    ) -> None:
        self._cluster_repo = cluster_repo
        self._stats_store = stats_store
        self._lead_repo = lead_repo

    def dead_ends(self, limit: int = 50) -> list[DeadEndGroup]:
        return self._cluster_repo.ranked(limit)

    def stats(self) -> VolumeStats:
        # Volume basics come from the question log; the lead count from the lead store.
        return replace(self._stats_store.volume_stats(), lead_count=len(self._lead_repo.list()))

    def leads(self) -> list[StoredLead]:
        return self._lead_repo.list()
