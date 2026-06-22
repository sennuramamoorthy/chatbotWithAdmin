"""Admin authentication primitives — pure and deterministic.

Single admin role (A-1): a configured username plus a *salted* password hash, and
stateless HMAC-signed session tokens whose expiry is checked against an injected
clock (never ``datetime.now()``). Python stdlib only — no external crypto deps.

The transport/wiring layers compose these via ``application/admin_auth.py``.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
from dataclasses import dataclass

# Work factor for PBKDF2. High enough to be a meaningful brute-force cost, low
# enough that the (few) auth calls per request stay fast and tests stay snappy.
_PBKDF2_ITERATIONS = 120_000


def hash_password(password: str, salt: str) -> str:
    """PBKDF2-HMAC-SHA256 hash of ``password`` under ``salt``, hex-encoded."""
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _PBKDF2_ITERATIONS)
    return digest.hex()


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    """Constant-time check that ``password`` hashes (under ``salt``) to the expected."""
    return hmac.compare_digest(hash_password(password, salt), expected_hash)


@dataclass(frozen=True)
class AdminUser:
    """The single configured admin: username + salted password hash (no plaintext)."""

    username: str
    salt: str
    password_hash: str


def admin_user_from_password(username: str, password: str, *, salt: str) -> AdminUser:
    """Build an ``AdminUser`` from a plaintext password (hashing it once, at wiring)."""
    return AdminUser(username=username, salt=salt, password_hash=hash_password(password, salt))


def check_credentials(username: str, password: str, user: AdminUser) -> bool:
    """True iff both username and password match (both compared in constant time)."""
    username_ok = hmac.compare_digest(username, user.username)
    password_ok = verify_password(password, user.salt, user.password_hash)
    return username_ok and password_ok


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text.encode())


def _sign(payload: str, secret: str) -> str:
    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
    return _b64(signature)


def issue_session_token(
    subject: str, *, secret: str, issued_at: dt.datetime, ttl_seconds: int
) -> str:
    """Mint ``<payload>.<signature>`` carrying the subject and an absolute expiry."""
    expiry = int(issued_at.timestamp()) + ttl_seconds
    payload = _b64(json.dumps({"sub": subject, "exp": expiry}).encode())
    return f"{payload}.{_sign(payload, secret)}"


def verify_session_token(token: str, *, secret: str, now: dt.datetime) -> str | None:
    """Return the token's subject if the signature is valid and it is unexpired, else None."""
    parts = token.split(".")
    if len(parts) != 2:
        return None
    payload, signature = parts
    if not hmac.compare_digest(signature, _sign(payload, secret)):
        return None
    try:
        claims = json.loads(_unb64(payload))
        expiry = int(claims["exp"])
        subject = str(claims["sub"])
    except (ValueError, KeyError, TypeError):
        return None
    if expiry <= int(now.timestamp()):
        return None
    return subject
