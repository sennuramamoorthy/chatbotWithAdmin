"""POST /api/v1/leads — validation routed through the domain rules (FR-11/12)."""

import pytest

pytestmark = pytest.mark.integration


def _payload(**overrides) -> dict:
    base = {"name": "Asha", "email": "asha@example.com", "consent": True}
    base.update(overrides)
    return base


def _errors_by_field(response) -> dict[str, str]:
    return {e["field"]: e["code"] for e in response.json()["errors"]}


def test_valid_lead_is_created(make_client, lead_repo):  # TC-018 (persistence)
    response = make_client().post(
        "/api/v1/leads", json=_payload(dead_end_question="What's the hostel fee?")
    )
    assert response.status_code == 201
    assert response.json()["lead_id"]

    stored = lead_repo.list()
    assert len(stored) == 1
    assert stored[0].dead_end_question == "What's the hostel fee?"
    assert stored[0].delivery_status == "pending"


def test_blank_name_is_rejected(make_client):  # TC-020
    response = make_client().post("/api/v1/leads", json=_payload(name="   "))
    assert response.status_code == 422
    assert _errors_by_field(response).get("name") == "required"


def test_invalid_email_no_phone_rejected_and_not_persisted(make_client, lead_repo):  # TC-021
    response = make_client().post(
        "/api/v1/leads", json={"name": "Asha", "email": "asdf@asdf", "consent": True}
    )
    assert response.status_code == 422
    assert _errors_by_field(response).get("email") == "invalid"
    assert lead_repo.list() == []


def test_consent_required(make_client):  # TC-025
    response = make_client().post("/api/v1/leads", json=_payload(consent=False))
    assert response.status_code == 422
    assert _errors_by_field(response).get("consent") == "required"


def test_phone_only_is_accepted(make_client):  # TC-023
    response = make_client().post(
        "/api/v1/leads", json={"name": "Asha", "phone": "9876543210", "consent": True}
    )
    assert response.status_code == 201
