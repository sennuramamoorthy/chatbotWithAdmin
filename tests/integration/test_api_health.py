"""Health endpoint — the widget uses this to decide soft-fail (AC-10.3)."""

import pytest

pytestmark = pytest.mark.integration


def test_health_ok(make_client):
    response = make_client().get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_cors_header_allows_cross_origin_embedding(make_client):
    # The widget is embedded on the university site and calls the API cross-origin.
    response = make_client().get(
        "/api/v1/health", headers={"origin": "https://takshashila.edu"}
    )
    assert response.headers["access-control-allow-origin"] == "*"
