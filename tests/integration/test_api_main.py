"""Smoke test for the dev/demo wiring — it must compose, serve, and run the loop."""

import pytest
from fastapi.testclient import TestClient

from takshashila_chatbot.api.main import app

pytestmark = pytest.mark.integration

ADMIN = {"Authorization": "Bearer demo-admin-token"}


def test_demo_app_serves_health_and_grounded_chat():
    client = TestClient(app)
    assert client.get("/api/v1/health").json()["status"] == "ok"

    grounded = client.post(
        "/api/v1/chat",
        json={"message": "What is the application and registration fee?", "session_id": "demo"},
    )
    assert grounded.status_code == 200
    assert "3000" in grounded.text  # grounded in the real admissions data (data/admissions.db)


def test_demo_learning_loop_surfaces_dead_ends():
    client = TestClient(app)

    # Off-topic question retrieves nothing -> dead-end, logged for the loop.
    dead_end = client.post(
        "/api/v1/chat", json={"message": "What is the weather today?", "session_id": "demo"}
    )
    assert '"outcome": "dead_end"' in dead_end.text

    # Admin triggers clustering and sees the gap ranked on the dashboard.
    assert client.post("/api/v1/admin/cluster", headers=ADMIN).json()["clustered"] >= 1
    groups = client.get("/api/v1/admin/dashboard/dead-ends", headers=ADMIN).json()["dead_ends"]
    assert any("weather" in g["question"].lower() for g in groups)
