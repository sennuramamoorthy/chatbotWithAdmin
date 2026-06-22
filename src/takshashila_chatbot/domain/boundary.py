"""Rule-based boundary pre-filter (FR-8, US-5).

A cheap, deterministic first layer that catches the high-precision cases —
prompt injection, profanity/abuse, and explicit competitor comparison — and
returns a canned, in-role response *without* spending an LLM call. Fuzzier cases
(e.g. off-topic homework) are handled by the system prompt and the grounding
gate, tested at the eval layer.

Detection favours precision: when in doubt the request is ALLOWed through to the
grounded pipeline rather than wrongly blocked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

# A representative moderation list; in production this is a maintained, possibly
# externalised list. Whole-word, case-insensitive matching is used.
DEFAULT_PROFANITY: frozenset[str] = frozenset(
    {
        "damn",
        "crap",
        "bastard",
        "bitch",
        "asshole",
        "shit",
        "fuck",
        "dick",
        "piss",
    }
)

_INJECTION_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"ignore\s+(all\s+|the\s+)?(previous|prior|above)\s+instructions?",
        r"disregard\s+(all\s+|the\s+)?(previous|prior|above)",
        r"forget\s+(your|all|the)\s+(instructions?|rules?|prompt)",
        r"you\s+are\s+now\b",
        r"\bact\s+as\b",
        r"system\s+prompt",
        r"reveal\s+(your|the)\s+(prompt|instructions?)",
        r"pretend\s+to\s+be",
    )
]

_COMPETITOR_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\b(better|worse|superior|inferior)\s+than\b",
        r"\b(compare|comparison|versus|vs\.?)\b.*\b(college|universit|institut|iit|nit)\b",
        r"\b(rank|ranking|ranked)\b.*\b(college|universit|institut)\b",
        r"\b(other|another|rival|competitor)\s+(college|universit|institut)",
    )
]

_REDIRECT = (
    "I can help with admissions & fees, placements, facilities, transport, "
    "courses, and faculty at Takshashila University. What would you like to know?"
)
_COMPETITOR_REPLY = (
    "I can only share factual information about Takshashila University, not "
    "comparisons with other institutions. What would you like to know about "
    "Takshashila?"
)
_ABUSE_REPLY = (
    "I'm here to help with questions about Takshashila University. Let me know "
    "what you'd like to know about admissions, courses, fees, and more."
)


class BoundaryVerdict(str, Enum):
    ALLOW = "allow"
    INJECTION = "injection"
    ABUSE = "abuse"
    COMPETITOR = "competitor"


@dataclass(frozen=True)
class BoundaryResult:
    verdict: BoundaryVerdict
    response: str | None = None  # canned reply when not ALLOW

    @property
    def allowed(self) -> bool:
        return self.verdict is BoundaryVerdict.ALLOW


def _matches_any(patterns: list[re.Pattern[str]], text: str) -> bool:
    return any(p.search(text) for p in patterns)


def _contains_profanity(text_lower: str, words: frozenset[str] | set[str]) -> bool:
    return any(
        re.search(rf"\b{re.escape(word)}\b", text_lower) for word in words
    )


def screen(
    text: str,
    *,
    profanity: frozenset[str] | set[str] = DEFAULT_PROFANITY,
) -> BoundaryResult:
    """Screen visitor input. Injection is checked first (security), then abuse,
    then competitor comparison; otherwise the input is allowed through."""
    lowered = text.lower()

    if _matches_any(_INJECTION_PATTERNS, text):
        return BoundaryResult(BoundaryVerdict.INJECTION, _REDIRECT)

    if _contains_profanity(lowered, profanity):
        return BoundaryResult(BoundaryVerdict.ABUSE, _ABUSE_REPLY)

    if _matches_any(_COMPETITOR_PATTERNS, text):
        return BoundaryResult(BoundaryVerdict.COMPETITOR, _COMPETITOR_REPLY)

    return BoundaryResult(BoundaryVerdict.ALLOW)
