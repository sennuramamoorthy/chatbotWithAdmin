"""Script-based language detection (FR-7).

A fast, deterministic pre-signal used to steer the reply language. It classifies
by *script* (Tamil vs Latin), which is exact for native-script input. Romanized
Tamil ("fees enna?") is Latin script and is left to the model + eval layer.
"""

from __future__ import annotations

from enum import Enum

# Unicode Tamil block.
_TAMIL_START, _TAMIL_END = 0x0B80, 0x0BFF


class Language(str, Enum):
    EN = "en"
    TA = "ta"
    MIXED = "mixed"
    UNKNOWN = "unknown"


def _is_tamil(ch: str) -> bool:
    return _TAMIL_START <= ord(ch) <= _TAMIL_END


def _is_latin_letter(ch: str) -> bool:
    return ("a" <= ch <= "z") or ("A" <= ch <= "Z")


def detect_language(text: str) -> Language:
    has_tamil = any(_is_tamil(ch) for ch in text)
    has_latin = any(_is_latin_letter(ch) for ch in text)

    if has_tamil and has_latin:
        return Language.MIXED
    if has_tamil:
        return Language.TA
    if has_latin:
        return Language.EN
    return Language.UNKNOWN
