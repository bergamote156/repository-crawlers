"""
Unit tests for `confline.resolution.error_records` — pure builders that
freeze the rendering data for resolution-time errors.

These builders are exercised end-to-end via `test_resolver.py`; this
file pins per-builder behaviour directly so hooks like the
"`Try one of` dedup" or the "skip None label" branches can't quietly
break under integration-test cover.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from confline.config.base import ConfigBase
from confline.config.schema import opt
from confline.resolution.context import ResolutionContext
from confline.resolution.error_records import (
    build_missing_field_record,
    build_source_value_record,
    build_suggestion_strings,
)
from confline.sources.base import NO_VALUE, Source
from confline.sources.cli_source import CliSource
from confline.sources.default_source import DefaultSource
from confline.sources.env_source import EnvSource


class _Cfg(ConfigBase):
    port: int = opt(8080)
    host: str = opt("localhost", excluded_from=[CliSource])


def _f(name: str):
    return _Cfg.__config_schema__.find_field(name)


# ─────────────────────────────────────────────────────────────────────────────
# build_source_value_record
# ─────────────────────────────────────────────────────────────────────────────


def test_source_value_record_excludes_active_source_from_suggestions():
    """The active source is the one that just failed — the renderer
    must not propose the form that produced the bad value, otherwise
    the operator's first 'fix' is the same channel they already tried."""
    from argparse import Namespace

    cli = CliSource(Namespace())
    env = EnvSource({})
    ctx = ResolutionContext(sources=(cli, env, DefaultSource()))

    record = build_source_value_record(
        _f("port"),
        raw_value="abc",
        active_source=env,
        source_label="environment",
        context=ctx,
    )

    assert record.path == "port"
    assert record.source_label == "environment"
    assert record.value == "abc"
    # Env (the failed source) is omitted; cli stays.
    assert any("--port" in s for s in record.suggestions)
    assert all("PORT=" not in s for s in record.suggestions)


def test_source_value_record_carries_source_native_key_from_active_source():
    """The active source is asked for its native key form (`--port`,
    `MYAPP_PORT`, …) so the error header can name what the operator
    actually typed, not the dotted schema path."""
    from argparse import Namespace

    cli = CliSource(Namespace())
    ctx = ResolutionContext(sources=(cli, DefaultSource()))

    record = build_source_value_record(
        _f("port"),
        raw_value="abc",
        active_source=cli,
        source_label="command line",
        context=ctx,
    )

    assert record.source_native_key == "--port"


def test_source_value_record_native_key_is_none_when_active_source_missing():
    """A source-less raise (e.g. validator firing post-resolution) has
    no active source — the native key is None and the renderer falls
    back to the schema path."""
    ctx = ResolutionContext(sources=(DefaultSource(),))

    record = build_source_value_record(
        _f("port"),
        raw_value=42,
        active_source=None,
        source_label=None,
        context=ctx,
    )

    assert record.source_native_key is None
    assert record.source_label is None


# ─────────────────────────────────────────────────────────────────────────────
# build_missing_field_record
# ─────────────────────────────────────────────────────────────────────────────


def test_missing_field_record_includes_every_eligible_source_in_suggestions():
    """Missing-required has no active source — `skip=None` keeps every
    eligible source in the chain."""
    from argparse import Namespace

    cli = CliSource(Namespace())
    env = EnvSource({}, prefix="MYAPP_")
    ctx = ResolutionContext(sources=(cli, env, DefaultSource()))

    record = build_missing_field_record(_f("port"), ctx)

    assert record.path == "port"
    assert any("--port" in s for s in record.suggestions)
    assert any("MYAPP_PORT" in s for s in record.suggestions)


def test_missing_field_record_suggestions_skip_excluded_sources():
    """`excluded_from` is honoured by the eligibility helper, so
    excluded sources don't appear in the missing-field hint either."""
    from argparse import Namespace

    cli = CliSource(Namespace())
    ctx = ResolutionContext(sources=(cli, DefaultSource()))

    # `host` excludes CliSource — the record must omit any --host line.
    record = build_missing_field_record(_f("host"), ctx)

    assert all("--host" not in s for s in record.suggestions)


# ─────────────────────────────────────────────────────────────────────────────
# build_suggestion_strings — focused on dedup + None label gates
# ─────────────────────────────────────────────────────────────────────────────


def test_suggestion_strings_dedup_identical_lines_across_sources():
    """Two sources that produce the same `<key><sep><example>` string
    appear once in the output — duplicate hint lines are noise."""

    class _AltDefault(Source):
        """Same separator and key shape as DefaultSource on a stringified path."""

        name = "alt-default"
        display_label = "alt-default"

        def resolve(self, field):  # noqa: ARG002
            return NO_VALUE

        def _describe_field(self, field):
            return ".".join(field.path)

    class _OtherDefault(Source):
        name = "other-default"
        display_label = "other-default"

        def resolve(self, field):  # noqa: ARG002
            return NO_VALUE

        def _describe_field(self, field):
            return ".".join(field.path)

    ctx = ResolutionContext(sources=(_AltDefault(), _OtherDefault(), DefaultSource()))
    suggestions = build_suggestion_strings(_f("port"), ctx, skip=None)

    matching = [s for s in suggestions if "port 8080" in s]
    assert len(matching) == 1, suggestions


def test_suggestion_strings_skip_source_with_none_label():
    """A source whose `describe_field` returns None has no addressable
    key form for this field — its line is omitted rather than rendered
    as a hollow `None 8080`."""

    class _NoLabelSource(Source):
        name = "no-label"
        display_label = "no-label"

        def resolve(self, field):  # noqa: ARG002
            return NO_VALUE

        def _describe_field(self, field):  # noqa: ARG002
            return None

    ctx = ResolutionContext(sources=(_NoLabelSource(), DefaultSource()))
    suggestions = build_suggestion_strings(_f("port"), ctx, skip=None)

    assert all("None" not in s for s in suggestions)


def test_suggestion_strings_respect_skip_argument():
    """`skip=source` is the active-source carve-out; the named source
    must not appear in the output regardless of eligibility."""
    from argparse import Namespace

    cli = CliSource(Namespace())
    env = EnvSource({}, prefix="MYAPP_")
    ctx = ResolutionContext(sources=(cli, env, DefaultSource()))

    skipping_cli = build_suggestion_strings(_f("port"), ctx, skip=cli)
    assert all("--port" not in s for s in skipping_cli)
    assert any("MYAPP_PORT" in s for s in skipping_cli)


def test_suggestion_strings_skip_sources_excluded_for_field():
    """`excluded_from` propagates into suggestion building — a source
    listed there cannot legitimately resolve the field, so it must not
    advertise a key form for it either."""
    from argparse import Namespace

    cli = CliSource(Namespace())
    env = EnvSource({}, prefix="MYAPP_")
    ctx = ResolutionContext(sources=(cli, env, DefaultSource()))

    suggestions = build_suggestion_strings(_f("host"), ctx, skip=None)

    # `host` excludes CliSource — no --host in suggestions, MYAPP_HOST stays.
    assert all("--host" not in s for s in suggestions)
    assert any("MYAPP_HOST" in s for s in suggestions)
