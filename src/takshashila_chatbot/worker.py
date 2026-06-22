"""Background worker entrypoint.

Runs the scheduled batch jobs of the learning loop — dead-end clustering and the
12-month retention purge — on an interval, using the deterministic Scheduler. The
loop body (``run_loop``) is unit-tested; ``main`` is the process entrypoint that
builds production services from the environment and runs forever (``make worker``).

Note: lead-email delivery is intentionally NOT scheduled here — the in-memory
outbox lives in the API process; scheduling it cross-process needs the durable
Postgres-backed outbox (a noted follow-up).
"""

from __future__ import annotations

from collections.abc import Callable

from .application.scheduler import Scheduler

# Default intervals (seconds): cluster dead-ends every 5 min, purge daily.
CLUSTER_INTERVAL = 300
RETENTION_INTERVAL = 86_400


def run_loop(
    scheduler: Scheduler,
    *,
    ticks: int,
    sleep_seconds: float,
    sleeper: Callable[[float], None],
) -> None:
    """Tick the scheduler ``ticks`` times, sleeping between ticks via ``sleeper``."""
    for _ in range(ticks):
        scheduler.tick()
        sleeper(sleep_seconds)


def main() -> None:  # pragma: no cover - process entrypoint (needs infra; runs forever)
    import os
    import time

    import httpx
    import psycopg

    from .adapters.connection_executor import ConnectionExecutor
    from .adapters.embeddings import HttpEmbedder
    from .adapters.pg_dead_end_cluster_repository import PgDeadEndClusterRepository
    from .adapters.pg_lead_repository import PgLeadRepository
    from .adapters.pg_question_log import PgQuestionLog
    from .application.dead_end_clustering import DeadEndClusteringService
    from .application.retention import RetentionService
    from .config import Settings
    from .domain.clock import SystemClock

    settings = Settings.from_env(os.environ)
    clock = SystemClock()
    executor = ConnectionExecutor(psycopg.connect(settings.database_url))
    embedder = HttpEmbedder(
        httpx.Client(base_url=settings.embeddings_base_url), model=settings.embeddings_model
    )
    question_log = PgQuestionLog(executor, clock)
    clustering = DeadEndClusteringService(
        question_log, embedder, PgDeadEndClusterRepository(executor)
    )
    retention = RetentionService(question_log, PgLeadRepository(executor), clock)

    scheduler = Scheduler(clock)
    scheduler.register("cluster_dead_ends", lambda: clustering.run(), CLUSTER_INTERVAL)
    scheduler.register("purge_retention", lambda: retention.purge(), RETENTION_INTERVAL)

    while True:
        scheduler.tick()
        time.sleep(30)


if __name__ == "__main__":  # pragma: no cover
    main()
