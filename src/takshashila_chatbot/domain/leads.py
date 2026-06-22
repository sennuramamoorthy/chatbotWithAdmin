"""Lead capture validation (FR-11, FR-12).

Rules (AC-7.2 / AC-7.4):
  * name is required;
  * at least one *valid* contact channel (email or Indian mobile);
  * a provided-but-invalid channel reports a field-specific error;
  * message capped at 1,000 chars;
  * explicit consent must be ticked.

Enforced server-side regardless of client behaviour. Returns a list of field
errors; an empty list means the lead is valid.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_MESSAGE_LEN = 1000

# Basic shape only (per FR-11): local@domain.tld with no spaces.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Indian mobile: optional +91 / 0 prefix, then 10 digits starting 6-9 (A-3).
_PHONE_RE = re.compile(r"^(?:\+91|0)?[6-9]\d{9}$")
_PHONE_STRIP_RE = re.compile(r"[\s\-()]")


@dataclass(frozen=True)
class LeadInput:
    name: str
    email: str | None = None
    phone: str | None = None
    program: str | None = None
    message: str | None = None
    consent: bool = False


@dataclass(frozen=True)
class FieldError:
    field: str
    code: str
    message: str


def is_valid_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(email.strip()))


def is_valid_indian_mobile(phone: str) -> bool:
    digits = _PHONE_STRIP_RE.sub("", phone)
    return bool(_PHONE_RE.match(digits))


def _blank(value: str | None) -> bool:
    return value is None or value.strip() == ""


def validate_lead(data: LeadInput) -> list[FieldError]:
    errors: list[FieldError] = []

    if _blank(data.name):
        errors.append(FieldError("name", "required", "Please enter your name."))

    email_present = not _blank(data.email)
    phone_present = not _blank(data.phone)
    email_ok = email_present and is_valid_email(data.email)  # type: ignore[arg-type]
    phone_ok = phone_present and is_valid_indian_mobile(data.phone)  # type: ignore[arg-type]

    if email_present and not email_ok:
        errors.append(
            FieldError("email", "invalid", "Please enter a valid email address.")
        )
    if phone_present and not phone_ok:
        errors.append(
            FieldError(
                "phone", "invalid", "Please enter a valid 10-digit Indian mobile number."
            )
        )

    # At least one valid channel is required. If nothing was supplied at all,
    # point at the contact requirement; if something was supplied but invalid,
    # the field-specific error(s) above already guide the fix (AC-7.4).
    if not (email_ok or phone_ok) and not email_present and not phone_present:
        errors.append(
            FieldError(
                "contact",
                "contact_required",
                "Please provide a valid email address or phone number.",
            )
        )

    if data.message is not None and len(data.message) > MAX_MESSAGE_LEN:
        errors.append(
            FieldError(
                "message",
                "too_long",
                f"Please keep your message under {MAX_MESSAGE_LEN} characters.",
            )
        )

    if not data.consent:
        errors.append(
            FieldError(
                "consent",
                "required",
                "Please tick consent so Admissions can follow up with you.",
            )
        )

    return errors


def is_valid_lead(data: LeadInput) -> bool:
    return validate_lead(data) == []
