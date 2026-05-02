"""
Cross-cutting integration tests — scenarios that touch more than one module
and don't naturally belong to any single test_<module> file.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import threading
from typing import Literal

import pytest

from confline import (
    CommandApp,
    ConfigBase,
    DefaultSource,
    EnvSource,
    MutuallyExclusiveGroup,
    SourceValueError,
    YamlSource,
    command,
    field_validator,
    load_config,
    opt,
)
from confline.errors import ConfigError, EnvKeyCollisionError
from confline.resolution.coerce import coerce, register_type

# ─────────────────────────────────────────────────────────────────────────────
# Idempotence — load_config × 2
# ─────────────────────────────────────────────────────────────────────────────


def test_load_config_twice_with_same_sources_yields_equivalent_configs():
    class Cfg(ConfigBase):
        host: str = opt("localhost")
        items: list[int] = opt(default_factory=lambda: [1, 2, 3])

    sources = [
        EnvSource({"HOST": "h"}),
        DefaultSource(),
    ]
    a = load_config(Cfg, sources=sources)
    b = load_config(Cfg, sources=sources)

    assert a.host == b.host
    assert a.items == b.items
    # default_factory must hand each instance its OWN list; mutating
    # `a.items` must not bleed into `b.items` on the next load.
    a.items.append(99)
    c = load_config(Cfg, sources=sources)
    assert 99 not in c.items


# ─────────────────────────────────────────────────────────────────────────────
# Nested mutex — MutuallyExclusiveGroup as a nested config
# ─────────────────────────────────────────────────────────────────────────────


class _NestedMode(MutuallyExclusiveGroup, required=False):
    json: bool = opt(False)
    yaml: bool = opt(False)


def test_nested_mutex_group_enforced_inside_outer_config():
    class Outer(ConfigBase):
        mode: _NestedMode = opt(default_factory=_NestedMode)
        host: str = opt("localhost")

    with pytest.raises(ConfigError, match="at most one"):
        load_config(
            Outer,
            sources=[
                YamlSource(scopes=[{"mode": {"json": True, "yaml": True}}]),
                DefaultSource(),
            ],
        )


# ─────────────────────────────────────────────────────────────────────────────
# Field validators — error translation and contract
# ─────────────────────────────────────────────────────────────────────────────


def test_field_validator_assertion_error_translated_to_source_value_error():
    class Cfg(ConfigBase):
        port: int = opt(8080)

        @field_validator("port")
        def _check(self, value):
            assert value < 10000, "port must be < 10000"
            return value

    with pytest.raises(SourceValueError) as excinfo:
        load_config(
            Cfg,
            sources=[EnvSource({"PORT": "60000"}), DefaultSource()],
        )
    assert "port" in str(excinfo.value)


def test_field_validator_key_error_translated_to_source_value_error():
    lookup = {"a": 1, "b": 2}

    class Cfg(ConfigBase):
        name: str = opt("a")

        @field_validator("name")
        def _check(self, value):
            return lookup[value]  # KeyError on unknown name

    with pytest.raises(SourceValueError):
        load_config(
            Cfg,
            sources=[EnvSource({"NAME": "missing"}), DefaultSource()],
        )


def test_field_validator_returning_wrong_type_is_passed_through_as_is():
    """Documents the contract: validators are *post-coerce* user code.
    A validator returning a value of the "wrong" type per the field
    annotation is not re-coerced or re-validated — it's the user's
    responsibility. This test pins the behaviour so a future refactor
    cannot silently change it."""

    class Cfg(ConfigBase):
        port: int = opt(8080)

        @field_validator("port")
        def _normalize(self, value):
            return f"port-{value}"  # returns str, not int

    cfg = load_config(Cfg, sources=[DefaultSource()])
    assert cfg.port == "port-8080"  # type: ignore[comparison-overlap]


# ─────────────────────────────────────────────────────────────────────────────
# EnvSource — boundary behaviour
# ─────────────────────────────────────────────────────────────────────────────


def test_env_source_ignores_keys_outside_prefix():
    """An env var with a different prefix must not bleed into the field
    value — even when its tail matches the field name."""

    class Cfg(ConfigBase):
        host: str = opt("default")

    cfg = load_config(
        Cfg,
        sources=[
            EnvSource(
                {"OTHER_HOST": "leaked", "MYAPP_HOST": "from-env"},
                prefix="MYAPP_",
            ),
            DefaultSource(),
        ],
    )
    assert cfg.host == "from-env"


def test_env_source_empty_string_treated_as_unset():
    """`PORT=` (empty) means "I deliberately did not set this in env."
    The next source in the chain wins."""

    class Cfg(ConfigBase):
        host: str = opt("from-default")

    cfg = load_config(
        Cfg,
        sources=[EnvSource({"HOST": ""}), DefaultSource()],
    )
    assert cfg.host == "from-default"


def test_env_key_collision_detected_with_underscore_delimiter():
    class Inner(ConfigBase):
        bar: str = opt("x")

    class Cfg(ConfigBase):
        foo: Inner = opt(default_factory=Inner)
        foo_bar: str = opt("y")  # collides with foo.bar under delimiter="_"

    with pytest.raises(EnvKeyCollisionError) as excinfo:
        load_config(
            Cfg,
            sources=[
                EnvSource({}, prefix="MYAPP_", delimiter="_"),
                DefaultSource(),
            ],
        )
    msg = str(excinfo.value)
    assert "MYAPP_FOO_BAR" in msg
    # Resolution hints — three named paths with rising blast radius.
    assert "Resolve by:" in msg
    assert "delimiter" in msg
    assert "EnvAlias" in msg
    assert "rename" in msg


def test_env_key_collision_silent_under_default_double_underscore():
    """Default delimiter `__` keeps `foo_bar` (single underscore in
    name) and `foo.bar` (nested) on separate keys: `FOO_BAR` vs
    `FOO__BAR`. No collision."""

    class Inner(ConfigBase):
        bar: str = opt("x")

    class Cfg(ConfigBase):
        foo: Inner = opt(default_factory=Inner)
        foo_bar: str = opt("y")

    cfg = load_config(
        Cfg,
        sources=[EnvSource({}, prefix="MYAPP_"), DefaultSource()],
    )
    assert cfg.foo.bar == "x"
    assert cfg.foo_bar == "y"


# ─────────────────────────────────────────────────────────────────────────────
# YamlSource — UTF-8 BOM tolerated
# ─────────────────────────────────────────────────────────────────────────────


def test_yaml_source_tolerates_utf8_bom(tmp_path):
    cfg_file = tmp_path / "app.yaml"
    cfg_file.write_bytes("﻿".encode() + b"host: from-bom\n")

    class Cfg(ConfigBase):
        host: str = opt("default")

    cfg = load_config(
        Cfg,
        sources=[YamlSource.from_files([cfg_file]), DefaultSource()],
    )
    assert cfg.host == "from-bom"


# ─────────────────────────────────────────────────────────────────────────────
# Coerce — literal chain exception
# ─────────────────────────────────────────────────────────────────────────────


def test_coerce_literal_chains_inner_cast_error():
    """When the inner cast fails (e.g. `int('foo')`) and the value is
    not in the literal set either, the original ValueError chains so
    Sentry/Datadog formatters see the underlying reason."""

    with pytest.raises(ValueError) as excinfo:
        coerce("not-a-number", Literal[1, 2, 3])

    # The chain: ValueError("not in {args}") from ValueError("invalid literal...")
    assert excinfo.value.__cause__ is not None
    assert "invalid literal" in str(excinfo.value.__cause__)


# ─────────────────────────────────────────────────────────────────────────────
# default_factory raise wrapping
# ─────────────────────────────────────────────────────────────────────────────


def test_default_factory_raise_wraps_in_source_value_error():
    """A factory raising at resolution time gets translated to a
    typed `SourceValueError` naming the field, instead of bubbling a
    raw exception out of `load_config`."""

    def boom():
        raise RuntimeError("env not ready")

    class Cfg(ConfigBase):
        connection: str = opt(default_factory=boom)

    with pytest.raises(SourceValueError) as excinfo:
        load_config(Cfg, sources=[DefaultSource()])
    assert "connection" in str(excinfo.value)


# ─────────────────────────────────────────────────────────────────────────────
# CommandApp — config-class inference with multi-arg handlers
# ─────────────────────────────────────────────────────────────────────────────


def test_infer_config_class_finds_config_after_other_args():
    """Handlers like `def serve(self, session: Ctx, config: Cfg)` work
    without explicit `config_class=` — the inference walks all args
    and picks the first ConfigBase."""

    class _Cfg(ConfigBase):
        target: str = opt("x")

    class Ctx:  # noqa: D401 — stub for the test.
        pass

    class App(CommandApp):
        @command()
        def serve(self, session: Ctx, config: _Cfg):  # noqa: ARG002
            return config.target

        def dispatch_command(self, command, config):
            # Provide a Ctx for the handler — default dispatch only
            # passes config; override to thread the extra arg.
            handler = getattr(self, command.method_name)
            return handler(Ctx(), config)

    assert App().run(["serve"]) == "x"


# ─────────────────────────────────────────────────────────────────────────────
# Public surface — confline.__init__ exports
# ─────────────────────────────────────────────────────────────────────────────


def test_init_exports_match_all_after_sectioning():
    """Every name imported at the top level of `confline/__init__.py`
    is in `__all__`. Sectioned imports drift over time — a defensive
    check catches the case where someone adds a new import block but
    forgets to extend `__all__`."""
    import inspect

    import confline

    # Reflectively gather what's bound on the package — type/function/
    # exception classes coming from confline's own modules.
    public_names: set[str] = set()
    for name, value in inspect.getmembers(confline):
        if name.startswith("_"):
            continue
        module = getattr(value, "__module__", "")
        if module.startswith("confline"):
            public_names.add(name)

    missing = public_names - set(confline.__all__)
    assert not missing, f"top-level imports missing from __all__: {sorted(missing)}"


def test_novalue_type_alias_is_not_public():
    """`NO_VALUE` is the only public sentinel contract."""
    import confline
    import confline.sources as confline_sources

    assert "NoValue" not in confline.__all__
    assert "NoValue" not in confline_sources.__all__
    assert not hasattr(confline, "NoValue")
    assert not hasattr(confline_sources, "NoValue")


# ─────────────────────────────────────────────────────────────────────────────
# register_type lock — smoke check, not a real race test
# ─────────────────────────────────────────────────────────────────────────────


def test_register_type_under_threads_does_not_deadlock():
    """Sanity: concurrent register_type calls complete under the lock."""

    class _T1:
        pass

    def worker():
        register_type(_T1, lambda s: _T1())

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=2.0)
    for t in threads:
        assert not t.is_alive()
