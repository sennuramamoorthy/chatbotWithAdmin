"""PgDeadEndClusterRepository — replace-all + frequency-ranked read."""

import pytest

from takshashila_chatbot.adapters.pg_dead_end_cluster_repository import (
    PgDeadEndClusterRepository,
)
from takshashila_chatbot.application.ports import DeadEndGroup
from takshashila_chatbot.testing.fakes import RecordingExecutor

pytestmark = pytest.mark.integration


def test_replace_all_clears_then_inserts_each():
    executor = RecordingExecutor()
    PgDeadEndClusterRepository(executor).replace_all(
        [DeadEndGroup("hostel", 5), DeadEndGroup("bus", 2)]
    )
    assert "delete from dead_end_clusters" in executor.calls[0][0].lower()
    assert "insert into dead_end_clusters" in executor.calls[1][0].lower()
    assert executor.calls[1][1] == ("hostel", 5)
    assert executor.calls[2][1] == ("bus", 2)


def test_ranked_maps_rows_and_passes_limit():
    executor = RecordingExecutor(results=[[("hostel", 5), ("bus", 2)]])
    groups = PgDeadEndClusterRepository(executor).ranked(10)
    assert groups == [DeadEndGroup("hostel", 5), DeadEndGroup("bus", 2)]
    assert executor.calls[0][1] == (10,)
