"""
Tests for the `Source` ABC contract and the `NO_VALUE` sentinel.

End-to-end behaviour of custom sources that affects rendering or
resolution lives next to its consumer:
- describe_provenance failure logging → tests/test_resolution/test_provenance.py
- display_label fallback in mutex rendering → tests/test_ui/test_errors.py
- display_kv_separator in error suggestions → tests/test_resolution/test_resolver.py
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from argparse import Namespace
from pathlib import Path

import pytest

from confline.config.base import ConfigBase
from confline.config.schema import ConfigFieldInfo, ConfigSchema, opt
from confline.sources.base import NO_VALUE, Source
from confline.sources.cli_source import CliSource
from confline.sources.default_source import DefaultSource
from confline.sources.env_source import EnvSource
from confline.sources.yaml_source import YamlSource

# ─────────────────────────────────────────────────────────────────────────────
# NO_VALUE sentinel
# ─────────────────────────────────────────────────────────────────────────────


def test_no_value_is_singleton():
    # Calling the type a second time returns the same instance — the sentinel
    # round-trips through `_NoValueType()` for callers that reach the type.
    assert NO_VALUE is type(NO_VALUE)()


def test_no_value_is_falsy():
    assert not NO_VALUE


def test_no_value_repr():
    assert repr(NO_VALUE) == "NO_VALUE"


# ─────────────────────────────────────────────────────────────────────────────
# Class-level constants on built-in sources
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("cls", "name"),
    [
        (CliSource, "argparse"),
        (EnvSource, "env"),
        (YamlSource, "yaml"),
        (DefaultSource, "default"),
    ],
)
def test_built_in_sources_carry_canonical_name(cls, name):
    assert cls.name == name


@pytest.mark.parametrize(
    ("cls", "label"),
    [
        (CliSource, "command line"),
        (EnvSource, "environment"),
        (YamlSource, "yaml"),
        (DefaultSource, "default"),
    ],
)
def test_built_in_sources_set_display_label(cls, label):
    assert cls.display_label == label


def test_display_label_required_on_subclasses():
    """`display_label` is a `ClassVar` without a default — accessing it on
    a subclass that omits the declaration raises `AttributeError`,
    surfacing the missing contract at first use rather than silently
    leaking `name` into operator-facing rendering."""

    class _NoLabel(Source):
        name = "vault"

        def resolve(self, field):  # noqa: ARG002
            return NO_VALUE

    with pytest.raises(AttributeError):
        _ = _NoLabel().display_label


def test_is_fallback_default_is_false_on_base():
    assert Source.is_fallback is False


def test_default_source_is_fallback_true():
    """`DefaultSource.is_fallback = True` is the contract that lets the
    mutex enforcer ignore declared defaults — a YAML setting two fields
    in a mutex group conflicts; defaults filling them do not."""
    assert DefaultSource.is_fallback is True


def test_display_in_help_block_default_is_true():
    """Plugin authors get visibility in `--help` for free; `CliSource`
    flips this off because the flag is already in argparse's action header."""
    assert Source.display_in_help_block is True
    assert CliSource.display_in_help_block is False
    assert EnvSource.display_in_help_block is True
    assert YamlSource.display_in_help_block is True
    assert DefaultSource.display_in_help_block is True


@pytest.mark.parametrize(
    ("cls", "separator"),
    [
        (CliSource, " "),
        (EnvSource, "="),
        (YamlSource, ": "),
        (DefaultSource, " "),  # inherits base default
    ],
)
def test_built_in_sources_set_display_kv_separator(cls, separator):
    assert cls.display_kv_separator == separator


# ─────────────────────────────────────────────────────────────────────────────
# Default method behaviour on the ABC
# ─────────────────────────────────────────────────────────────────────────────


class _Plain(Source):
    """Minimal concrete subclass exercising the base defaults."""

    name = "plain"
    display_label = "plain"

    def resolve(self, field):  # noqa: ARG002
        return NO_VALUE


class _Cfg(ConfigBase):
    host: str = opt("default")
    no_plain: str = opt("default", excluded_from=[_Plain])


def _f(name: str) -> ConfigFieldInfo:
    result = _Cfg.__config_schema__.find_field(name)
    assert result is not None
    return result


def test_supports_field_default_returns_true():
    """`Source.supports_field` is True by default so plugin authors get
    full participation. Sources with shape limits override (argparse/env
    skip `list[ConfigBase]`)."""
    assert _Plain.supports_field(_f("host")) is True


def test_validate_schema_default_is_no_op():
    schema: ConfigSchema = _Cfg.__config_schema__
    assert _Plain().validate_schema(schema) is None


def test_describe_field_default_returns_none():
    assert _Plain().describe_field(_f("host")) is None


def test_describe_field_applies_excluded_from_guard():
    """`describe_field` short-circuits to `None` when the source's
    concrete class is listed in `field.excluded_from`, without ever
    calling `_describe_field`."""

    class _Custom(Source):
        name = "custom"
        display_label = "custom"

        def resolve(self, field):  # noqa: ARG002
            return NO_VALUE

        def _describe_field(self, field):  # noqa: ARG002
            return "custom-key"

    class C(ConfigBase):
        included: str = opt("default")
        excluded: str = opt("default", excluded_from=[_Custom])

    src = _Custom()
    assert src.describe_field(C.__config_schema__.find_field("included")) == "custom-key"
    assert src.describe_field(C.__config_schema__.find_field("excluded")) is None


def test_describe_provenance_default_returns_none():
    assert _Plain().describe_provenance(_f("host")) is None


def test_describe_unset_hint_default_returns_none():
    assert _Plain().describe_unset_hint("anything") is None


# ─────────────────────────────────────────────────────────────────────────────
# Built-in sources' provenance falls back to display_label
# ─────────────────────────────────────────────────────────────────────────────


def _builtins() -> list[tuple[Source, str]]:
    return [
        (CliSource(Namespace()), "command line"),
        (EnvSource({}), "environment"),
        (YamlSource(scopes=[]), "yaml"),
        (DefaultSource(), "default"),
    ]


@pytest.mark.parametrize(("source", "expected_label"), _builtins())
def test_built_in_describe_provenance_returns_none(
    source: Source,
    expected_label: str,
):
    """No built-in source carries per-instance provenance by default —
    only `YamlSource.from_files` does. The renderer falls back to
    `display_label` for everything else."""
    field = _f("host")
    assert source.describe_provenance(field) is None
    assert source.display_label == expected_label


# ─────────────────────────────────────────────────────────────────────────────
# FileOrigin
# ─────────────────────────────────────────────────────────────────────────────


def test_file_origin_is_frozen_with_optional_origin_label():
    from dataclasses import FrozenInstanceError

    from confline.sources.base import FileOrigin

    o1 = FileOrigin(path=Path("/etc/app.yaml"))
    assert o1.origin is None

    o2 = FileOrigin(path=Path("/etc/app.yaml"), origin="cli")
    assert o2.origin == "cli"

    with pytest.raises(FrozenInstanceError):
        o2.origin = "env"  # type: ignore[misc]
