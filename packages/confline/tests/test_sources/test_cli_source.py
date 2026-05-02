"""
Tests for `CliSource`, `CliAlias`, and the `CliPositional` marker.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import dataclasses
from typing import Annotated

import pytest

from confline.config.base import ConfigBase
from confline.config.schema import opt
from confline.sources.base import NO_VALUE
from confline.sources.cli_source import CliAlias, CliPositional, CliSource
from tests.helpers.fixtures import make_namespace


class _Cfg(ConfigBase):
    host: str = opt("localhost")
    nested_field: int = opt(0)
    excluded: str = opt("default", excluded_from=[CliSource])


def _f(name: str):
    return _Cfg.__config_schema__.find_field(name)


# ─────────────────────────────────────────────────────────────────────────────
# CliAlias marker
# ─────────────────────────────────────────────────────────────────────────────


def test_cli_alias_requires_at_least_one_name():
    with pytest.raises(ValueError, match="at least one name"):
        CliAlias()


def test_cli_alias_equality_and_hash_are_value_based():
    """`CliAlias` is hand-written rather than `@dataclass(frozen=True)`
    because the `*names` constructor matters more than dataclass
    boilerplate. Equality/hash must still behave as a value type so
    `Annotated` metadata can be deduplicated."""
    a = CliAlias("-c", "--config")
    b = CliAlias("-c", "--config")
    c = CliAlias("--config")

    assert a == b
    assert hash(a) == hash(b)
    assert a != c
    assert a != "CliAlias('-c', '--config')"


def test_cli_alias_repr_lists_names():
    assert repr(CliAlias("-c", "--config")) == "CliAlias('-c', '--config')"


# ─────────────────────────────────────────────────────────────────────────────
# resolve()
# ─────────────────────────────────────────────────────────────────────────────


def test_resolve_reads_value_by_dotted_path():
    src = CliSource(make_namespace(host="from-cli"))
    assert src.resolve(_f("host")) == "from-cli"


def test_resolve_returns_no_value_for_missing_attribute():
    """Builder uses `argparse.SUPPRESS` so unset flags don't appear in
    the namespace — that absence becomes `NO_VALUE`, not the type-default."""
    src = CliSource(make_namespace())
    assert src.resolve(_f("host")) is NO_VALUE


def test_resolve_walks_dotted_path_for_nested_view():
    """Loader prepends the parent prefix and passes a full-path view —
    a single namespace covers nested configs without name collisions."""
    f = dataclasses.replace(_f("nested_field"), path=("db", "nested_field"))
    src = CliSource(make_namespace(**{"db.nested_field": 42}))
    assert src.resolve(f) == 42


def test_resolve_returns_namespace_value_unchanged():
    """Argparse may have already coerced via `type=int` — source returns
    the value verbatim and lets the loader's coercion stage decide."""
    src = CliSource(make_namespace(nested_field=99))
    assert src.resolve(_f("nested_field")) == 99


# ─────────────────────────────────────────────────────────────────────────────
# from_argv() factory
# ─────────────────────────────────────────────────────────────────────────────


def test_from_argv_builds_parser_and_parses():
    src = CliSource.from_argv(_Cfg, ["--host", "from-argv"])
    assert src.resolve(_f("host")) == "from-argv"


def test_from_argv_excluded_field_not_addressable():
    """`excluded_from=[CliSource]` removes the flag from the auto-built
    parser entirely — the field cannot be supplied through CLI even by
    spelling the flag manually."""
    src = CliSource.from_argv(_Cfg, [])
    assert src.resolve(_f("excluded")) is NO_VALUE


# ─────────────────────────────────────────────────────────────────────────────
# supports_field — argparse cannot encode list[ConfigBase]
# ─────────────────────────────────────────────────────────────────────────────


def test_supports_field_rejects_list_of_config_base():
    """Argparse has no flat-flag form for list-of-dicts. YAML carries
    that shape natively; CLI must self-skip so the parser builder never
    has to invent an encoding."""

    class Item(ConfigBase):
        name: str = opt("x")

    class Cfg(ConfigBase):
        items: list[Item] = opt(default_factory=list)
        host: str = opt("localhost")

    items = Cfg.__config_schema__.find_field("items")
    host = Cfg.__config_schema__.find_field("host")

    assert CliSource.supports_field(items) is False
    assert CliSource.supports_field(host) is True


# ─────────────────────────────────────────────────────────────────────────────
# describe_field()
# ─────────────────────────────────────────────────────────────────────────────


def test_describe_field_uses_dotted_path_by_default():
    src = CliSource(make_namespace())
    assert src.describe_field(_f("host")) == "--host"


def test_describe_field_returns_none_when_excluded():
    src = CliSource(make_namespace())
    assert src.describe_field(_f("excluded")) is None


def test_describe_field_honors_cli_alias():
    class C(ConfigBase):
        config_path: Annotated[str, CliAlias("-c", "--config")] = opt("a.yml")

    src = CliSource(make_namespace())
    f = C.__config_schema__.find_field("config_path")
    assert src.describe_field(f) == "-c"


def test_describe_field_for_nested_field_uses_dashed_path():
    """Underscores convert to dashes the same way `argparse_builder`
    derives flag names — `--db.nested-field`, so help/error fallbacks
    match what argparse actually accepts."""
    src = CliSource(make_namespace())
    f = dataclasses.replace(_f("nested_field"), path=("db", "nested_field"))
    assert src.describe_field(f) == "--db.nested-field"


def test_describe_field_for_positional_uses_metavar():
    """Positionals don't have a flag form — their label is the last
    path segment as upper metavar, matching argparse's usage line."""
    class C(ConfigBase):
        input_path: Annotated[str, CliPositional] = opt("in.txt")

    field = C.__config_schema__.find_field("input_path")
    assert CliSource(make_namespace()).describe_field(field) == "INPUT_PATH"


# ─────────────────────────────────────────────────────────────────────────────
# describe_unset_hint()
# ─────────────────────────────────────────────────────────────────────────────


def test_unset_hint_distinguishes_flags_and_positionals():
    src = CliSource(make_namespace())
    assert src.describe_unset_hint("--host") == " — remove --host"
    assert src.describe_unset_hint("HOST") == " — remove the HOST argument"
