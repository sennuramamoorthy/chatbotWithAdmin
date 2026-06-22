"""AdminAuth — composes the auth domain with a clock for login + request guarding.

Covers the legacy/break-glass service token, username+password login, token
acceptance, expiry, and the locked-down empty config.
"""

import datetime as dt

import pytest

from takshashila_chatbot.application.admin_auth import AdminAuth
from takshashila_chatbot.domain.auth import admin_user_from_password
from takshashila_chatbot.domain.clock import IST, FixedClock

pytestmark = pytest.mark.integration

USER = admin_user_from_password("admin", "s3cret", salt="admin")


def _clock() -> FixedClock:
    return FixedClock(dt.datetime(2026, 6, 21, 9, 0, tzinfo=IST))


def test_login_returns_a_token_that_authorize_accepts():
    auth = AdminAuth(user=USER, secret="sign", clock=_clock(), ttl_seconds=3600)
    assert auth.login_enabled is True
    assert auth.ttl_seconds == 3600

    token = auth.login("admin", "s3cret")
    assert token is not None
    assert auth.authorize(f"Bearer {token}") is True


def test_login_rejects_wrong_username_or_password():
    auth = AdminAuth(user=USER, secret="sign", clock=_clock())
    assert auth.login("admin", "wrong") is None
    assert auth.login("intruder", "s3cret") is None


def test_login_disabled_without_a_user():
    auth = AdminAuth(service_token="svc")
    assert auth.login_enabled is False
    assert auth.login("admin", "s3cret") is None


def test_login_disabled_without_a_signing_secret():
    auth = AdminAuth(user=USER)  # user set, but no secret/service token to sign with
    assert auth.login_enabled is False
    assert auth.login("admin", "s3cret") is None


def test_service_token_is_accepted_as_break_glass():
    auth = AdminAuth(service_token="svc", user=USER, secret="sign", clock=_clock())
    assert auth.authorize("Bearer svc") is True


def test_authorize_rejects_missing_malformed_and_invalid_tokens():
    auth = AdminAuth(service_token="svc", user=USER, secret="sign", clock=_clock())
    assert auth.authorize(None) is False
    assert auth.authorize("Basic xyz") is False  # not a Bearer scheme
    assert auth.authorize("Bearer not-a-real-token") is False


def test_session_token_expires_after_ttl():
    clock = _clock()
    auth = AdminAuth(user=USER, secret="sign", clock=clock, ttl_seconds=60)
    token = auth.login("admin", "s3cret")
    clock.advance(61)
    assert auth.authorize(f"Bearer {token}") is False


def test_empty_config_locks_everything():
    auth = AdminAuth()  # no service token, no user, no secret
    assert auth.login_enabled is False
    assert auth.authorize("Bearer anything") is False
