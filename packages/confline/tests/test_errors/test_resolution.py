"""
Tests for resolution-time error classes and their pre-computed value
records:

- `SourceValueRecord`/`SourceValueError`
- `MissingFieldRecord`/`MissingRequiredError`
- `ProvidedField`/`MutexViolationError`

Records are frozen value snapshots — once raised, the error survives
being passed to logging sinks or rendered later without retaining live
schema, source, or `ConfigBase` references.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import FrozenInstanceError

import pytest

from confline.errors import (
    MissingFieldRecord,
    MissingRequiredError,
    MutexViolationError,
    ProvidedField,
    SourceValueError,
    SourceValueRecord,
)


def _value_record(  # noqa: PLR0913 — wraps a 7-field frozen record
    path: str = "db.port",
    *,
    type_desc: str = "int",
    secret: bool = False,
    source_label: str | None = "environment",
    source_native_key: str | None = None,
    value: object = None,
    suggestions: tuple[str, ...] = (),
) -> SourceValueRecord:
    return SourceValueRecord(
        path=path,
        type_desc=type_desc,
        secret=secret,
        source_label=source_label,
        source_native_key=source_native_key,
        value=value,
        suggestions=suggestions,
    )


def _provided(  # noqa: PLR0913 — wraps a 6-field frozen record
    path: str = "port",
    *,
    secret: bool = False,
    source_name: str = "argparse",
    source_label: str = "command line",
    source_native_key: str | None = "--port",
    value: object = 8080,
) -> ProvidedField:
    return ProvidedField(
        path=path,
        secret=secret,
        source_name=source_name,
        source_label=source_label,
        source_native_key=source_native_key,
        value=value,
    )


# ─────────────────────────────────────────────────────────────────────────────
# SourceValueRecord — frozen snapshot
# ─────────────────────────────────────────────────────────────────────────────


def test_source_value_record_is_frozen():
    """`@dataclass(frozen=True, slots=True)` so the record cannot be
    mutated after raise — protects log sinks and structured handlers
    from drift between capture and render."""
    rec = _value_record()
    with pytest.raises(FrozenInstanceError):
        rec.path = "other"  # type: ignore[misc]


# ─────────────────────────────────────────────────────────────────────────────
# SourceValueError — message composition
# ─────────────────────────────────────────────────────────────────────────────


def test_source_value_error_with_field_record_includes_field_and_source_in_message():
    err = SourceValueError(
        "bad int",
        field_record=_value_record(path="db.port", source_label="environment"),
    )
    msg = str(err)

    assert msg.startswith("bad int")
    assert "field=db.port" in msg
    assert "source=environment" in msg


def test_source_value_error_carries_detail_and_record_attributes():
    rec = _value_record(path="db.port", source_label="environment", value="abc")
    err = SourceValueError("bad int", field_record=rec)

    assert err.detail == "bad int"
    assert err.field_record is rec
    assert err.field_record.value == "abc"


def test_source_value_error_without_record_keeps_detail_clean():
    err = SourceValueError("plain")
    assert str(err) == "plain"
    assert err.field_record is None


def test_source_value_error_omits_source_clause_when_record_has_no_source_label():
    """A field validator running after resolution has no active source —
    `source_label=None` skips the `source=...` ctx item rather than
    rendering `source=None`."""
    err = SourceValueError(
        "validator failed",
        field_record=_value_record(path="port", source_label=None),
    )
    msg = str(err)

    assert "field=port" in msg
    assert "source=" not in msg


# ─────────────────────────────────────────────────────────────────────────────
# MissingFieldRecord — frozen snapshot
# ─────────────────────────────────────────────────────────────────────────────


def test_missing_field_record_is_frozen():
    rec = MissingFieldRecord(path="host", type_desc="string", suggestions=())
    with pytest.raises(FrozenInstanceError):
        rec.path = "other"  # type: ignore[misc]


# ─────────────────────────────────────────────────────────────────────────────
# MissingRequiredError — message composition
# ─────────────────────────────────────────────────────────────────────────────


def test_missing_required_error_lists_every_missing_field():
    err = MissingRequiredError(
        [
            MissingFieldRecord(path="host", type_desc="string", suggestions=()),
            MissingFieldRecord(path="port", type_desc="int", suggestions=()),
        ],
        sources_tried=("env", "default"),
    )

    msg = str(err)
    assert "host" in msg
    assert "port" in msg


def test_missing_required_error_appends_sources_tried_suffix():
    err = MissingRequiredError(
        [MissingFieldRecord(path="host", type_desc="string", suggestions=())],
        sources_tried=("env", "default"),
    )
    assert "(sources tried: env, default)" in str(err)


def test_missing_required_error_omits_sources_tried_suffix_when_chain_empty():
    """An empty chain (e.g. error raised before sources were materialised)
    must not render `(sources tried: )` — the renderer treats absence
    distinct from empty."""
    err = MissingRequiredError(
        [MissingFieldRecord(path="host", type_desc="string", suggestions=())],
    )
    assert "sources tried" not in str(err)


def test_missing_required_error_normalises_sequences_to_tuples():
    err = MissingRequiredError(
        [MissingFieldRecord(path="host", type_desc="string", suggestions=())],
        sources_tried=["env"],
    )
    assert isinstance(err.fields, tuple)
    assert isinstance(err.sources_tried, tuple)


# ─────────────────────────────────────────────────────────────────────────────
# ProvidedField — frozen snapshot
# ─────────────────────────────────────────────────────────────────────────────


def test_provided_field_is_frozen():
    pf = _provided()
    with pytest.raises(FrozenInstanceError):
        pf.path = "other"  # type: ignore[misc]


# ─────────────────────────────────────────────────────────────────────────────
# MutexViolationError — message composition
# ─────────────────────────────────────────────────────────────────────────────


def test_mutex_required_message_uses_exactly_one():
    """A `required=True` group asks for exactly one provider — the
    message must read 'exactly one of [...]' so the operator knows
    silence is not a valid answer either."""
    err = MutexViolationError(
        group_name="_Mode",
        field_paths=["a", "b"],
        provided=[],
        required=True,
    )
    msg = str(err)
    assert "exactly one of [a, b]" in msg
    assert "(got 0)" in msg


def test_mutex_optional_message_uses_at_most_one():
    """`required=False` allows zero — the message reads 'at most one'
    so an operator with both set knows the fix is to drop one, not
    add a third."""
    err = MutexViolationError(
        group_name="_Mode",
        field_paths=["a", "b"],
        provided=[_provided(path="a"), _provided(path="b", source_native_key="--b")],
        required=False,
    )
    msg = str(err)
    assert "at most one of [a, b]" in msg
    assert "(got 2)" in msg


def test_mutex_violation_error_carries_structured_attributes():
    err = MutexViolationError(
        group_name="_Mode",
        field_paths=["a", "b"],
        provided=[_provided(path="a")],
        required=False,
    )
    assert err.group_name == "_Mode"
    assert err.field_paths == ("a", "b")
    assert isinstance(err.provided, tuple)
    assert err.provided[0].path == "a"
    assert err.required is False
