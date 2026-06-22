"""Log-only EmailSender (FR-13).

A dependency-free ``EmailSender`` that writes the message via stdlib ``logging``
instead of talking to SMTP. Used by the dev entrypoint and tests so the outbox /
retry path (EC-18) is exercisable without a mail server. It always succeeds.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class LogEmailSender:
    def send(self, to: str, subject: str, body: str) -> None:
        logger.info("email to=%s subject=%s body=%s", to, subject, body)
