"""Lead form validation (FR-11, FR-12). Covers TC-020..TC-025, EC-12..EC-17."""

import pytest

from takshashila_chatbot.domain.leads import (
    LeadInput,
    is_valid_email,
    is_valid_indian_mobile,
    is_valid_lead,
    validate_lead,
)

pytestmark = pytest.mark.unit


def _codes_by_field(errors):
    return {e.field: e.code for e in errors}


# --- channel format helpers -------------------------------------------------


@pytest.mark.parametrize("email", ["a@b.co", "student.name@takshashila.ac.in"])
def test_valid_emails(email):
    assert is_valid_email(email) is True


@pytest.mark.parametrize("email", ["asdf@asdf", "asdf", "@b.com", "a@b", "a b@c.com"])
def test_invalid_emails(email):
    assert is_valid_email(email) is False


@pytest.mark.parametrize(
    "phone", ["9876543210", "+919876543210", "09876543210", "98765 43210", "98765-43210"]
)
def test_valid_indian_mobiles(phone):
    assert is_valid_indian_mobile(phone) is True


@pytest.mark.parametrize("phone", ["1234567", "5876543210", "12345", "98765432100", "abcdefghij"])
def test_invalid_indian_mobiles(phone):
    assert is_valid_indian_mobile(phone) is False


# --- whole-lead validation --------------------------------------------------


def test_valid_lead_with_email():
    errors = validate_lead(LeadInput(name="Asha", email="asha@example.com", consent=True))
    assert errors == []


def test_valid_lead_with_phone_only():  # TC-023 / EC-15
    errors = validate_lead(LeadInput(name="Asha", phone="9876543210", consent=True))
    assert errors == []


def test_name_blank_is_rejected():  # TC-020 / EC-12
    errors = validate_lead(LeadInput(name="   ", email="a@b.co", consent=True))
    assert _codes_by_field(errors).get("name") == "required"


def test_invalid_email_and_no_phone_is_rejected():  # TC-021 / EC-13
    errors = validate_lead(LeadInput(name="Asha", email="asdf@asdf", consent=True))
    codes = _codes_by_field(errors)
    assert codes.get("email") == "invalid"
    assert errors != []  # no lead created


def test_implausible_phone_is_rejected():  # TC-022 / EC-14
    errors = validate_lead(LeadInput(name="Asha", phone="1234567", consent=True))
    assert _codes_by_field(errors).get("phone") == "invalid"


def test_no_contact_channel_is_rejected():
    errors = validate_lead(LeadInput(name="Asha", consent=True))
    assert _codes_by_field(errors).get("contact") == "contact_required"


def test_message_over_1000_chars_is_rejected():  # TC-024 / EC-16
    errors = validate_lead(
        LeadInput(name="Asha", email="a@b.co", message="x" * 1001, consent=True)
    )
    assert _codes_by_field(errors).get("message") == "too_long"


def test_message_exactly_1000_chars_is_accepted():
    errors = validate_lead(
        LeadInput(name="Asha", email="a@b.co", message="x" * 1000, consent=True)
    )
    assert errors == []


def test_consent_not_ticked_is_rejected():  # TC-025 / EC-17
    errors = validate_lead(LeadInput(name="Asha", email="a@b.co", consent=False))
    assert _codes_by_field(errors).get("consent") == "required"


def test_multiple_errors_are_all_reported():
    errors = validate_lead(LeadInput(name="", consent=False))
    codes = _codes_by_field(errors)
    assert codes.get("name") == "required"
    assert codes.get("consent") == "required"
    assert codes.get("contact") == "contact_required"


def test_is_valid_lead_helper():
    assert is_valid_lead(LeadInput(name="Asha", email="a@b.co", consent=True)) is True
    assert is_valid_lead(LeadInput(name="", consent=False)) is False
