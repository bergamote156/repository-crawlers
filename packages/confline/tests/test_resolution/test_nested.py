"""
Regression tests for nested-config resolution across all sources.

The path-derived dest (CLI), delimiter-joined uppercase (ENV) and dict
walk (YAML) must all converge on the same logical address.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from confline import (
    CliSource,
    ConfigBase,
    DefaultSource,
    EnvSource,
    YamlSource,
    load_config,
    opt,
)
from tests.helpers.assertions import assert_field_resolved_from


class HostConfig(ConfigBase):
    addr: str = opt("localhost")
    port: int = opt(5432)


class PoolConfig(ConfigBase):
    size: int = opt(10)
    timeout: float = opt(30.0)


class DbConfig(HostConfig, PoolConfig):
    """Composition + inheritance — DbConfig inherits both groups."""

    name: str = opt("app")


class AuthConfig(ConfigBase):
    user: str = opt("admin")
    password: str = opt("", secret=True)


class App(ConfigBase):
    db: DbConfig = opt(default_factory=DbConfig)
    auth: AuthConfig = opt(default_factory=AuthConfig)
    workers: int = opt(4)


# ─── CLI ───


def test_nested_cli_three_levels_deep():
    """`--db.addr` reaches DbConfig.addr (inherited from HostConfig)."""
    src = CliSource.from_argv(App, ["--db.addr", "remote", "--workers", "8"])
    cfg = load_config(App, sources=[src, DefaultSource()])
    assert cfg.db.addr == "remote"
    assert cfg.workers == 8
    assert_field_resolved_from(cfg, "db.addr", "argparse")


# ─── ENV ───


def test_nested_env_uses_double_underscore_delimiter():
    cfg = load_config(
        App,
        sources=[
            EnvSource({
                "DB__ADDR": "from-env",
                "DB__PORT": "9999",
                "AUTH__USER": "alice",
            }),
            DefaultSource(),
        ],
    )
    assert cfg.db.addr == "from-env"
    assert cfg.db.port == 9999
    assert cfg.auth.user == "alice"
    assert_field_resolved_from(cfg, "db.addr", "env")
    assert_field_resolved_from(cfg, "auth.user", "env")


def test_nested_env_with_prefix():
    cfg = load_config(
        App,
        sources=[
            EnvSource({"APP_DB__ADDR": "prefixed"}, prefix="APP_"),
            DefaultSource(),
        ],
    )
    assert cfg.db.addr == "prefixed"


def test_nested_env_custom_delimiter():
    cfg = load_config(
        App,
        sources=[
            EnvSource({"DB_ADDR": "single-underscore"}, delimiter="_"),
            DefaultSource(),
        ],
    )
    assert cfg.db.addr == "single-underscore"


# ─── YAML ───


def test_nested_yaml_dict_walk_via_field_path():
    cfg = load_config(
        App,
        sources=[
            YamlSource(scopes=[{
                "db": {"addr": "yaml-host", "port": 6543},
                "auth": {"user": "yaml-user"},
                "workers": 16,
            }]),
            DefaultSource(),
        ],
    )
    assert cfg.db.addr == "yaml-host"
    assert cfg.db.port == 6543
    assert cfg.auth.user == "yaml-user"
    assert cfg.workers == 16


# ─── Cross-source priority ───


def test_cli_overrides_env_overrides_yaml_for_nested_fields():
    cfg = load_config(
        App,
        sources=[
            CliSource.from_argv(App, ["--db.addr=cli-addr"]),
            EnvSource({"DB__ADDR": "env-addr", "DB__PORT": "1111"}),
            YamlSource(scopes=[{"db": {"addr": "yaml-addr", "port": 2222, "name": "yaml-name"}}]),
            DefaultSource(),
        ],
    )
    assert cfg.db.addr == "cli-addr"  # cli wins
    assert cfg.db.port == 1111  # env wins (no cli flag)
    assert cfg.db.name == "yaml-name"  # yaml wins (no cli/env)
    assert_field_resolved_from(cfg, "db.addr", "argparse")
    assert_field_resolved_from(cfg, "db.port", "env")
    assert_field_resolved_from(cfg, "db.name", "yaml")


# ─── Validator firing under composition ───


def test_nested_validator_fires_before_parent_validator():
    from confline.config.validators import model_validator

    fire_order: list[str] = []

    class Inner(ConfigBase):
        @model_validator
        def _inner_check(self):
            fire_order.append("inner")

    class Middle(ConfigBase):
        inner: Inner = opt(default_factory=Inner)

        @model_validator
        def _middle_check(self):
            fire_order.append("middle")

    class Outer(ConfigBase):
        middle: Middle = opt(default_factory=Middle)

        @model_validator
        def _outer_check(self):
            fire_order.append("outer")

    load_config(Outer, sources=[DefaultSource()])
    # Depth-first: inner → middle → outer.
    assert fire_order == ["inner", "middle", "outer"]
