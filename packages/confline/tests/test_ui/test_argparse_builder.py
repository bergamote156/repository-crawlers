"""
Tests for the argparse parser builder.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from enum import Enum
from pathlib import Path
from typing import Annotated, Literal

import pytest

from confline.config.base import ConfigBase, MutuallyExclusiveGroup
from confline.config.schema import opt
from confline.sources.cli_source import CliAlias, CliSource
from confline.ui.argparse_builder import build_argparse_parser


class Role(Enum):
    ADMIN = "admin"
    USER = "user"


def test_emits_dotted_dest_for_nested_field():
    class Db(ConfigBase):
        host: str = opt("localhost")

    class App(ConfigBase):
        db: Db = opt(default_factory=Db)

    parser = build_argparse_parser(App)
    ns = parser.parse_args(["--db.host=remote"])
    assert vars(ns) == {"db.host": "remote"}


def test_namespace_only_carries_user_provided_keys():
    """`default=SUPPRESS` keeps the namespace from filling in defaults."""

    class C(ConfigBase):
        host: str = opt("localhost")
        port: int = opt(8080)

    parser = build_argparse_parser(C)
    ns = parser.parse_args(["--host=remote"])
    assert vars(ns) == {"host": "remote"}
    # port is NOT in vars(ns) — user didn't pass it.
    assert "port" not in vars(ns)


def test_int_field_is_coerced_by_argparse():
    class C(ConfigBase):
        port: int = opt(8080)

    parser = build_argparse_parser(C)
    ns = parser.parse_args(["--port=9000"])
    assert ns.port == 9000
    assert isinstance(ns.port, int)


def test_bool_uses_boolean_optional_action():
    class C(ConfigBase):
        flag: bool = opt(False)

    parser = build_argparse_parser(C)
    ns = parser.parse_args(["--flag"])
    assert ns.flag is True
    ns = parser.parse_args(["--no-flag"])
    assert ns.flag is False


def test_cli_alias_overrides_auto_flag():
    class C(ConfigBase):
        config_file: Annotated[Path, CliAlias("-c", "--config")] = opt(Path("/tmp"))

    parser = build_argparse_parser(C)
    ns = parser.parse_args(["-c", "/etc/app.yaml"])
    assert ns.config_file == Path("/etc/app.yaml")


def test_excluded_field_does_not_appear_in_parser():
    class C(ConfigBase):
        api_key: str = opt("default", excluded_from=[CliSource])

    parser = build_argparse_parser(C)
    with pytest.raises(SystemExit):
        parser.parse_args(["--api-key=x"])


def test_list_of_config_base_field_not_emitted_as_flag():
    """`list[ConfigBase]` is list-of-dicts shape — CliSource declares
    incapability via `supports_field`, so the parser never advertises
    the field. YAML carries it natively; this guards that the
    source-side capability check fires from argparse_builder."""

    class Inner(ConfigBase):
        x: int = opt(0)

    class App(ConfigBase):
        items: list[Inner] = opt(default_factory=list)

    parser = build_argparse_parser(App)
    with pytest.raises(SystemExit):
        parser.parse_args(["--items=[]"])


def test_enum_choices_accepted():
    class C(ConfigBase):
        role: Role = opt(Role.USER)

    parser = build_argparse_parser(C)
    ns = parser.parse_args(["--role", "admin"])
    assert ns.role is Role.ADMIN


def test_literal_choices_validated():
    class C(ConfigBase):
        mode: Literal["dev", "prod"] = opt("dev")

    parser = build_argparse_parser(C)
    ns = parser.parse_args(["--mode", "prod"])
    assert ns.mode == "prod"
    with pytest.raises(SystemExit):
        parser.parse_args(["--mode", "test"])


def test_list_field_uses_append_action():
    class C(ConfigBase):
        tags: list[str] = opt(default_factory=list)

    parser = build_argparse_parser(C)
    ns = parser.parse_args(["--tags", "a", "--tags", "b"])
    assert ns.tags == ["a", "b"]


def test_heterogeneous_tuple_per_position():
    class C(ConfigBase):
        coords: tuple[int, str] = opt(default=(0, "origin"))

    parser = build_argparse_parser(C)
    ns = parser.parse_args(["--coords", "5", "north"])
    assert ns.coords == (5, "north")


def test_variadic_tuple_uses_nargs_star():
    class C(ConfigBase):
        nums: tuple[int, ...] = opt(default_factory=tuple)

    parser = build_argparse_parser(C)
    ns = parser.parse_args(["--nums", "1", "2", "3"])
    assert ns.nums == [1, 2, 3]
    # NB: argparse stores as list under nargs="*"; coerce() turns it
    # into a tuple when load_config reads it.


def test_count_field_increments_on_each_occurrence():
    class C(ConfigBase):
        verbose: int = opt(0, count=True)

    parser = build_argparse_parser(C)
    ns = parser.parse_args(["--verbose", "--verbose", "--verbose"])
    assert ns.verbose == 3


def test_count_missing_does_not_set_attr():
    class C(ConfigBase):
        verbose: int = opt(0, count=True)

    parser = build_argparse_parser(C)
    ns = parser.parse_args([])
    assert "verbose" not in vars(ns)


def test_mutex_group_argparse_enforces_exclusivity():
    class OutputMode(MutuallyExclusiveGroup, required=False):
        json: bool = opt(False)
        yaml: bool = opt(False)

    # `MutuallyExclusiveGroup` already extends `ConfigBase`; mixing
    # both in the bases would trigger an MRO conflict.
    class App(OutputMode):
        pass

    parser = build_argparse_parser(App)
    ns = parser.parse_args(["--json"])
    assert ns.json is True
    with pytest.raises(SystemExit):
        parser.parse_args(["--json", "--yaml"])


def test_mutex_argparse_does_not_enforce_required_at_parse_time():
    """`required=True` is enforced post-resolution by confline (so YAML/ENV
    can satisfy the constraint); argparse stays permissive at parse time."""

    class OutputMode(MutuallyExclusiveGroup, required=True):
        json: bool = opt(False)
        yaml: bool = opt(False)

    parser = build_argparse_parser(OutputMode)
    ns = parser.parse_args([])
    # argparse does not raise — the required check runs later.
    assert vars(ns) == {}


def test_emit_rejects_reserved_dest_command():
    """Field paths colliding with confline meta-flag dests must fail
    at parser build — silent shadowing of `_command` would make the
    subcommand effectively un-routable."""

    class C(ConfigBase):
        _command: str = opt("x")  # noqa: PLC2403 — testing collision

    with pytest.raises(ValueError, match="reserved CLI dest"):
        build_argparse_parser(C)


def test_emit_rejects_reserved_dest_config_files():
    class C(ConfigBase):
        _config_files: list[str] = opt(default_factory=list)

    with pytest.raises(ValueError, match="reserved CLI dest"):
        build_argparse_parser(C)


def test_command_app_mode_emits_subparsers():
    from confline import CommandApp, command
    from confline.ui.argparse_builder import build_command_app_parser

    class RegConfig(ConfigBase):
        target: str = opt("default")

    class App(CommandApp):
        @command()
        def register(self, config: RegConfig):
            return config.target

    parser = build_command_app_parser(spec=App()._cli_spec())
    ns = parser.parse_args(["register", "--target", "x"])
    assert ns._command == "register"
    assert ns.target == "x"


def test_metavar_carried_to_argparse():
    class C(ConfigBase):
        count: int = opt(0, metavar="N")

    parser = build_argparse_parser(C)
    help_str = parser.format_help()
    assert "--count N" in help_str


def test_nested_inherited_config_emits_one_argument_group_per_mro_level():
    """A nested field whose type composes via inheritance produces one
    argparse argument group per contributing class in the MRO. The
    group name embeds the dotted prefix and the contributing class name
    so the operator can locate where each field originated."""

    class HostConfig(ConfigBase):
        addr: str = opt("localhost")

    class PoolConfig(ConfigBase):
        size: int = opt(10)

    class DbConfig(HostConfig, PoolConfig):
        name: str = opt("app")

    class App(ConfigBase):
        db: DbConfig = opt(default_factory=DbConfig)

    help_str = build_argparse_parser(App).format_help()

    assert "db (HostConfig)" in help_str
    assert "db (PoolConfig)" in help_str
    assert "db (DbConfig)" in help_str
