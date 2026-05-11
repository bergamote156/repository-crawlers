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
    ConfigBase,
    DefaultSource,
    EnvSource,
    MutuallyExclusiveGroup,
    SourceValueError,
    YamlSource,
    load_config,
    opt,
)
from confline.errors import ConfigError
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
