"""Admin auth domain — salted password hashing and signed session tokens.

Pure and deterministic (the token clock is injected), so this security spine is
exhaustively unit-tested: correct/incorrect passwords, credential matching, token
round-trip, expiry, wrong-secret, tampering, and malformed input.
"""

import base64
import datetime as dt
import hashlib
import hmac

import pytest

from takshashila_chatbot.domain.auth import (
    admin_user_from_password,
    check_credentials,
    hash_password,
    issue_session_token,
    verify_password,
    verify_session_token,
)
from takshashila_chatbot.domain.clock import IST

pytestmark = pytest.mark.unit

WHEN = dt.datetime(2026, 6, 21, 9, 0, tzinfo=IST)


def _signed(payload_b64: str, secret: str) -> str:
    """Mirror the module's signing so we can forge a validly-signed-but-bad payload."""
    sig = hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).digest()
    return f"{payload_b64}.{base64.urlsafe_b64encode(sig).decode()}"


# --- password hashing -------------------------------------------------------


def test_hash_is_deterministic_salted_and_never_plaintext():
    assert hash_password("s3cret", "saltA") == hash_password("s3cret", "saltA")
    assert hash_password("s3cret", "saltA") != hash_password("s3cret", "saltB")
    assert hash_password("s3cret", "saltA") != "s3cret"


def test_verify_password_accepts_correct_and_rejects_wrong():
    digest = hash_password("hunter2", "pepper")
    assert verify_password("hunter2", "pepper", digest) is True
    assert verify_password("wrong", "pepper", digest) is False


# --- credentials ------------------------------------------------------------


def test_check_credentials_requires_matching_username_and_password():
    user = admin_user_from_password("admin", "letmein", salt="x")
    assert check_credentials("admin", "letmein", user) is True
    assert check_credentials("admin", "nope", user) is False  # wrong password
    assert check_credentials("intruder", "letmein", user) is False  # wrong username


# --- session tokens ---------------------------------------------------------


def test_token_round_trips_subject_before_expiry():
    token = issue_session_token("admin", secret="sign", issued_at=WHEN, ttl_seconds=3600)
    assert verify_session_token(token, secret="sign", now=WHEN) == "admin"
    assert (
        verify_session_token(token, secret="sign", now=WHEN + dt.timedelta(minutes=59))
        == "admin"
    )


def test_token_expires_at_ttl():
    token = issue_session_token("admin", secret="sign", issued_at=WHEN, ttl_seconds=3600)
    assert verify_session_token(token, secret="sign", now=WHEN + dt.timedelta(hours=2)) is None


def test_token_rejected_under_a_different_secret():
    token = issue_session_token("admin", secret="sign", issued_at=WHEN, ttl_seconds=3600)
    assert verify_session_token(token, secret="forged", now=WHEN) is None


def test_token_rejects_malformed_and_tampered_input():
    assert verify_session_token("", secret="sign", now=WHEN) is None
    assert verify_session_token("no-dot", secret="sign", now=WHEN) is None
    assert verify_session_token("a.b.c", secret="sign", now=WHEN) is None  # too many parts
    # Valid signature over a non-JSON payload -> decode error path.
    forged = _signed(base64.urlsafe_b64encode(b"not json").decode(), "sign")
    assert verify_session_token(forged, secret="sign", now=WHEN) is None
