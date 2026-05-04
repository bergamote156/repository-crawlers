"""
Unit tests for `confline.resolution.context` — the threaded resolution
context plus eligibility/safe-describe helpers.

These helpers are exercised end-to-end via `test_resolver.py`; the unit
tests here pin the contract of each helper directly so a regression in
the eligibility rule or a swallowed exception in a `safe_describe_*`
call doesn't have to wait for an integration test to surface.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import logging
from dataclasses import FrozenInstanceError

import pytest

from confline.config.base import ConfigBase
from confline.config.schema import opt
from confline.resolution.context import (
    ResolutionContext,
    is_source_eligible,
    safe_describe_field,
    safe_describe_provenance,
)
from confline.sources.base import NO_VALUE, Source
from confline.sources.cli_source import CliSource
from confline.sources.default_source import DefaultSource


class _Cfg(ConfigBase):
    host: str = opt("localhost")
    no_cli: str = opt("default", excluded_from=[CliSource])


def _f(name: str):
    return _Cfg.__config_schema__.find_field(name)


# ─────────────────────────────────────────────────────────────────────────────
# ResolutionContext — frozen snapshot of the source chain
# ─────────────────────────────────────────────────────────────────────────────


def test_resolution_context_normalises_sources_to_tuple():
    """A list is acceptable input but the stored chain is a tuple — the
    context is a frozen snapshot, so a caller mutating the original list
    later cannot affect resolution mid-flight."""
    sources = [DefaultSource()]
    ctx = ResolutionContext(sources=tuple(sources))
    assert isinstance(ctx.sources, tuple)


def test_resolution_context_is_frozen():
    ctx = ResolutionContext(sources=(DefaultSource(),))
    with pytest.raises(FrozenInstanceError):
        ctx.sources = ()  # type: ignore[misc]


# ─────────────────────────────────────────────────────────────────────────────
# is_source_eligible — excluded_from + supports_field
# ─────────────────────────────────────────────────────────────────────────────


def test_is_source_eligible_true_for_unrestricted_field():
    assert is_source_eligible(_f("host"), DefaultSource()) is True


def test_is_source_eligible_false_when_source_class_excluded():
    """`excluded_from=[CliSource]` blocks the field at the loader level
    — the source isn't asked about it. Pre-empts buggy custom sources
    from leaking the field via `resolve()` despite the user's opt-out."""
    from argparse import Namespace

    assert is_source_eligible(_f("no_cli"), CliSource(Namespace())) is False


def test_is_source_eligible_false_when_source_lacks_capability():
    """`supports_field=False` is the source-side declaration (e.g.
    argparse refuses `list[ConfigBase]`). Centralised here so the
    resolver and the suggestion builder stay in lock-step on the rule."""
    from argparse import Namespace

    class Item(ConfigBase):
        x: int = opt(0)

    class Cfg(ConfigBase):
        items: list[Item] = opt(default_factory=list)

    items = Cfg.__config_schema__.find_field("items")
    # CliSource self-skips list-of-ConfigBase via supports_field.
    assert is_source_eligible(items, CliSource(Namespace())) is False


# ─────────────────────────────────────────────────────────────────────────────
# safe_describe_field — defensive try/except + DEBUG log
# ─────────────────────────────────────────────────────────────────────────────


def test_safe_describe_field_returns_value_on_success():
    """Happy path passes the source's label through verbatim — the
    wrapper adds nothing to the output, only protection against raise."""
    from argparse import Namespace

    src = CliSource(Namespace())
    assert safe_describe_field(src, _f("host")) == "--host"


def test_safe_describe_field_returns_none_when_source_raises(caplog):
    """A buggy `describe_field` cannot break resolution; the wrapper
    swallows the raise, returns None, and logs at DEBUG with stack info
    so a maintainer raising the level can still diagnose the source."""

    class _ExplodingSource(Source):
        name = "exploding"
        display_label = "exploding"

        def resolve(self, field):  # noqa: ARG002
            return NO_VALUE

        def describe_field(self, field):  # noqa: ARG002
            raise RuntimeError("describe_field is broken")

    with caplog.at_level(logging.DEBUG, logger="confline"):
        result = safe_describe_field(_ExplodingSource(), _f("host"))

    assert result is None
    matching = [r for r in caplog.records if "describe_field failed" in r.getMessage()]
    assert matching, "expected DEBUG log naming the failed describe_field"
    assert matching[0].exc_info is not None


# ─────────────────────────────────────────────────────────────────────────────
# safe_describe_provenance — three branches: str, None, raise
# ─────────────────────────────────────────────────────────────────────────────


def test_safe_describe_provenance_returns_string_when_source_provides_one():
    """A source that supplies per-instance context (`yaml /etc/app.yml`)
    has its return string passed through unchanged."""

    class _LabelledSource(Source):
        name = "labelled"
        display_label = "labelled"

        def resolve(self, field):  # noqa: ARG002
            return NO_VALUE

        def describe_provenance(self, field):  # noqa: ARG002
            return "labelled /etc/app.yml"

    label = safe_describe_provenance(_LabelledSource(), _f("host"))
    assert label == "labelled /etc/app.yml"


def test_safe_describe_provenance_falls_back_to_display_label_for_none_result():
    """Default contract: `None` from `describe_provenance` means 'no
    per-instance info, use the class label'. The wrapper resolves the
    fallback so call sites don't repeat the None-check."""
    src = DefaultSource()
    assert safe_describe_provenance(src, _f("host")) == src.display_label


def test_safe_describe_provenance_falls_back_to_display_label_on_raise(caplog):
    """A buggy `describe_provenance` is treated identically to a `None`
    return — the label is helpful metadata, not a reason to abort
    resolution. Logs at DEBUG with stack info."""

    class _BuggySource(Source):
        name = "buggy"
        display_label = "buggy fallback"

        def resolve(self, field):  # noqa: ARG002
            return NO_VALUE

        def describe_provenance(self, field):  # noqa: ARG002
            raise RuntimeError("describe_provenance is broken")

    with caplog.at_level(logging.DEBUG, logger="confline"):
        label = safe_describe_provenance(_BuggySource(), _f("host"))

    assert label == "buggy fallback"
    matching = [r for r in caplog.records if "describe_provenance failed" in r.getMessage()]
    assert matching, "expected DEBUG log naming the failed describe_provenance"
    assert matching[0].exc_info is not None
