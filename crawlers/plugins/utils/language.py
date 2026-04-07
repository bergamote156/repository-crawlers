"""Language code normalization helpers."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from crawlers.ui import console

# Common natural-language names mapped to ISO 639-3 codes.
# Extend as more crawlers encounter additional languages.
_LANGUAGE_NAME_MAP: dict[str, str] = {
    "english": "eng",
    "polish": "pol",
}


def normalize_language_code(language: str | None, default: str = "eng") -> str:
    """
    Normalize a language string to an ISO 639-1/639-3 code.

    - Empty/None returns ``default``.
    - Known names ("English", "Polish", ...) are mapped to ISO 639-3 codes.
    - 2- or 3-letter alphabetic strings are passed through lowercased.
    - Anything else logs a warning and returns ``default``.
    """
    if not language:
        return default

    lowered = language.lower().strip()
    if lowered in _LANGUAGE_NAME_MAP:
        return _LANGUAGE_NAME_MAP[lowered]

    if len(lowered) in (2, 3) and lowered.isalpha():
        return lowered

    console.warning(
        f"Unknown language '{language}', defaulting to '{default}'. "
        "Consider extending the language map."
    )
    return default