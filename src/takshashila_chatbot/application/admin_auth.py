"""Admin authentication service — composes the auth domain with a clock.

Two ways in, one role (A-1):
  * a **service token** — the existing static admin token, kept for backward
    compatibility and machine/break-glass access;
  * interactive **username + password login**, which mints a short-lived signed
    session token (the credential the login UI uses thereafter).

The transport guard calls ``authorize`` on every admin request; the login
endpoint calls ``login``. Time is injected (``Clock``) so token expiry is testable.
"""

from __future__ import annotations

import hmac

from ..domain.auth import (
    AdminUser,
    check_credentials,
    issue_session_token,
    verify_session_token,
)
from ..domain.clock import Clock, SystemClock

_DEFAULT_TTL_SECONDS = 8 * 3600  # an 8-hour admin session


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        return ""
    return authorization[len("Bearer ") :].strip()


class AdminAuth:
    def __init__(
        self,
        *,
        service_token: str = "",
        user: AdminUser | None = None,
        secret: str = "",
        clock: Clock | None = None,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    ) -> None:
        self._service_token = service_token
        self._user = user
        # Session tokens are signed with ``secret``; fall back to the service token
        # so a single configured value enables both paths.
        self._secret = secret or service_token
        self._clock = clock or SystemClock()
        self._ttl = ttl_seconds

    @property
    def login_enabled(self) -> bool:
        return self._user is not None and bool(self._secret)

    @property
    def ttl_seconds(self) -> int:
        return self._ttl

    def login(self, username: str, password: str) -> str | None:
        """Validate credentials; on success return a fresh signed session token."""
        if self._user is None or not self._secret:
            return None
        if not check_credentials(username, password, self._user):
            return None
        return issue_session_token(
            username, secret=self._secret, issued_at=self._clock.now(), ttl_seconds=self._ttl
        )

    def authorize(self, authorization: str | None) -> bool:
        """True iff the Authorization header carries a valid service or session token."""
        token = _bearer(authorization)
        if not token:
            return False
        if self._service_token and hmac.compare_digest(token, self._service_token):
            return True
        if not self._secret:
            return False
        return verify_session_token(token, secret=self._secret, now=self._clock.now()) is not None
