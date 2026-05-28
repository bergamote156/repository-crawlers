"""
Tests for cross-cutting types and constants:
- `SECRET_PLACEHOLDER` (the redaction marker)
- `MISSING_DEFAULT` (public alias of `dataclasses.MISSING`)
- `FieldPath` (tuple-of-str type alias)

The `Provenance` value record's frozen contract is exercised in
`tests/test_resolution/test_provenance.py` next to its consumer.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import MISSING

from confline import SECRET_PLACEHOLDER
from confline.config import MISSING_DEFAULT


def test_secret_placeholder_is_six_asterisks():
    """A single canonical placeholder for redacted secret values across
    the framework — repr, error rendering, and structured logging all
    converge on this exact string. Pinned so refactors can't drift it."""
    assert SECRET_PLACEHOLDER == "******"


def test_missing_default_is_dataclasses_missing_sentinel():
    """`MISSING_DEFAULT` is aliased — not redefined — so users
    introspecting `ConfigFieldInfo.default` can compare against the
    same object the schema build uses internally. Identity check, not
    equality."""
    assert MISSING_DEFAULT is MISSING
