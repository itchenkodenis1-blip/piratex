"""Lightweight language detection based on Unicode character ranges.

No external dependencies — uses character frequency heuristics to determine
if a transcript is in the same language as the target output language.
"""

import unicodedata

# Mapping: target_language code → function that checks if text is in that language
# Each function returns True if the majority of alphabetic chars belong to the script

_CYRILLIC_RANGE = set(range(0x0400, 0x0500))
_CJK_RANGES = [range(0x4E00, 0x9FFF), range(0x3400, 0x4DBF)]
_ARABIC_RANGE = set(range(0x0600, 0x06FF))
_DEVANAGARI_RANGE = set(range(0x0900, 0x097F))


def _script_ratio(text: str, target_set: set[int] | None = None, category_prefix: str | None = None) -> float:
    """Return the fraction of alphabetic characters matching the given script."""
    alpha_count = 0
    match_count = 0
    for ch in text:
        if unicodedata.category(ch).startswith("L"):  # Letter
            alpha_count += 1
            cp = ord(ch)
            if target_set and cp in target_set:
                match_count += 1
            elif category_prefix and unicodedata.category(ch).startswith(category_prefix):
                match_count += 1
    if alpha_count == 0:
        return 0.0
    return match_count / alpha_count


def _is_cyrillic(text: str) -> bool:
    return _script_ratio(text, target_set=_CYRILLIC_RANGE) > 0.5


def _is_latin(text: str) -> bool:
    """Check if text is predominantly Latin script (en, fr, de, pt, es, etc.)."""
    alpha_count = 0
    latin_count = 0
    for ch in text:
        if unicodedata.category(ch).startswith("L"):
            alpha_count += 1
            if unicodedata.name(ch, "").startswith("LATIN"):
                latin_count += 1
    if alpha_count == 0:
        return False
    return latin_count / alpha_count > 0.5


# Languages that use Latin script
_LATIN_LANGUAGES = {"en", "fr", "de", "pt", "es", "it", "nl", "pl", "tr"}


def detect_same_language(transcript: str, target_language: str) -> bool:
    """Detect if the transcript is likely in the same language as target_language.

    Uses Unicode script heuristics — not perfect, but covers the main cases:
    - Russian transcript + target "ru" → True
    - English transcript + target "en" → True
    - English transcript + target "ru" → False
    - Russian transcript + target "en" → False

    For Latin-script languages (en, fr, de, pt), we can only detect that
    the transcript is Latin-based. This is a deliberate trade-off:
    fr→en adaptation is less common, and even when it happens the languages
    are different enough that some uniqueness comes naturally.
    """
    if not transcript or len(transcript.strip()) < 20:
        return False

    sample = transcript[:3000]

    if target_language == "ru":
        return _is_cyrillic(sample)

    if target_language in _LATIN_LANGUAGES:
        return _is_latin(sample)

    return False
