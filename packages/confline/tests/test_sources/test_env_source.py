"""
Tests for `EnvSource` and the `EnvAlias` marker.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import dataclasses
from typing import Annotated

import pytest

from confline.config.base import ConfigBase
from confline.config.schema import opt
from confline.errors import EnvKeyCollisionError
from confline.sources.base import NO_VALUE
from confline.sources.env_source import EnvAlias, EnvSource


class _Cfg(ConfigBase):
    host: str = opt("localhost")
    api_key: Annotated[str, EnvAlias("LEGACY_KEY")] = opt("default")
    no_env: str = opt("default", excluded_from=[EnvSource])


def _f(name: str):
    return _Cfg.__config_schema__.find_field(name)


# ─────────────────────────────────────────────────────────────────────────────
# resolve()
# ─────────────────────────────────────────────────────────────────────────────


def test_default_naming_uppercases_field_name():
    src = EnvSource({"HOST": "from-env"})
    assert src.resolve(_f("host")) == "from-env"


def test_prefix_prepends_to_var_name():
    src = EnvSource({"APP_HOST": "prefixed"}, prefix="APP_")
    assert src.resolve(_f("host")) == "prefixed"


def test_alias_overrides_derivation():
    src = EnvSource({"LEGACY_KEY": "secret"})
    assert src.resolve(_f("api_key")) == "secret"


def test_alias_ignores_prefix():
    """`EnvAlias("LEGACY_KEY")` is a literal — the prefix does not
    apply, so deployments can wire pre-existing env vars without
    renaming them."""
    src = EnvSource(
        {"LEGACY_KEY": "secret", "APP_API_KEY": "prefixed"},
        prefix="APP_",
    )
    assert src.resolve(_f("api_key")) == "secret"


def test_prefix_rejects_keys_with_wrong_prefix():
    """A var with a different prefix must not bleed into the field —
    even when its tail matches the field name."""
    src = EnvSource({"OTHER_HOST": "leaked", "MYAPP_HOST": "from-env"}, prefix="MYAPP_")
    assert src.resolve(_f("host")) == "from-env"


def test_empty_string_treated_as_no_value():
    """Colloquial 'not set' in shell — `PORT=` should fall through, not
    coerce to empty string. Apps that need literal-empty semantics
    override at a higher layer."""
    src = EnvSource({"HOST": ""})
    assert src.resolve(_f("host")) is NO_VALUE


def test_missing_var_returns_no_value():
    src = EnvSource({})
    assert src.resolve(_f("host")) is NO_VALUE


def test_nested_path_uses_default_double_underscore_delimiter():
    f = dataclasses.replace(_f("host"), path=("db", "host"))
    src = EnvSource({"DB__HOST": "deep"})
    assert src.resolve(f) == "deep"


def test_custom_delimiter():
    f = dataclasses.replace(_f("host"), path=("db", "host"))
    src = EnvSource({"DB_HOST": "deep"}, delimiter="_")
    assert src.resolve(f) == "deep"


# ─────────────────────────────────────────────────────────────────────────────
# supports_field — env vars cannot encode list[ConfigBase]
# ─────────────────────────────────────────────────────────────────────────────


def test_supports_field_rejects_list_of_config_base():
    """Env vars are flat string key/value — list-of-dicts has no
    canonical encoding here. YAML carries that shape natively."""

    class Item(ConfigBase):
        name: str = opt("x")

    class Cfg(ConfigBase):
        items: list[Item] = opt(default_factory=list)
        host: str = opt("localhost")

    items = Cfg.__config_schema__.find_field("items")
    host = Cfg.__config_schema__.find_field("host")

    assert EnvSource.supports_field(items) is False
    assert EnvSource.supports_field(host) is True


# ─────────────────────────────────────────────────────────────────────────────
# describe_field()
# ─────────────────────────────────────────────────────────────────────────────


def test_describe_field_returns_full_var_name():
    src = EnvSource({}, prefix="APP_")
    assert src.describe_field(_f("host")) == "APP_HOST"


def test_describe_field_honors_alias():
    src = EnvSource({}, prefix="APP_")
    assert src.describe_field(_f("api_key")) == "LEGACY_KEY"


def test_describe_field_returns_none_when_excluded():
    src = EnvSource({})
    assert src.describe_field(_f("no_env")) is None


def test_describe_field_uses_delimiter_for_nested():
    src = EnvSource({}, prefix="APP_")
    f = dataclasses.replace(_f("host"), path=("db", "host"))
    assert src.describe_field(f) == "APP_DB__HOST"


# ─────────────────────────────────────────────────────────────────────────────
# describe_unset_hint()
# ─────────────────────────────────────────────────────────────────────────────


def test_unset_hint_uses_unset_imperative():
    """The mutex error renderer composes per-source action hints; for
    env vars the imperative is `unset NAME`, distinct from CLI's
    `remove --name`."""
    assert EnvSource({}).describe_unset_hint("MYAPP_HOST") == " — unset MYAPP_HOST"


# ─────────────────────────────────────────────────────────────────────────────
# validate_schema() — collision detection
# ─────────────────────────────────────────────────────────────────────────────


def test_validate_schema_detects_underscore_collision():
    """`foo_bar` (top-level) and nested `foo.bar` collapse to the same
    `FOO_BAR` env var when the delimiter is `_`. Schema-only check
    catches this without needing a full `load_config`."""

    class Inner(ConfigBase):
        bar: str = opt("default")

    class C(ConfigBase):
        foo_bar: str = opt("default")
        foo: Inner = opt(default_factory=Inner)

    with pytest.raises(EnvKeyCollisionError) as exc:
        EnvSource({}, prefix="MYAPP_", delimiter="_").validate_schema(C.__config_schema__)
    err = exc.value
    assert err.source_native_key == "MYAPP_FOO_BAR"
    assert {err.field_a, err.field_b} == {"foo_bar", "foo.bar"}
    msg = str(err)
    assert "Resolve by:" in msg
    assert "delimiter" in msg
    assert "EnvAlias" in msg
    assert "rename" in msg


def test_validate_schema_no_collision_with_double_underscore_delimiter():
    """`__` delimiter keeps `foo_bar` and nested `foo.bar` on separate
    keys (`FOO_BAR` vs `FOO__BAR`), so both fields coexist without
    collision."""

    class Inner(ConfigBase):
        bar: str = opt("x")

    class C(ConfigBase):
        foo: Inner = opt(default_factory=Inner)
        foo_bar: str = opt("y")

    EnvSource({}, prefix="MYAPP_").validate_schema(C.__config_schema__)


def test_validate_schema_passes_for_disjoint_keys():
    class C(ConfigBase):
        host: str = opt("localhost")
        port: int = opt(8080)

    EnvSource({}).validate_schema(C.__config_schema__)


def test_validate_schema_skips_walk_for_collision_free_default_delimiter(monkeypatch):
    """Optimisation: with delimiter `__` and no underscores in any path
    component, a collision is mathematically impossible, so the walk is
    skipped. We assert this by replacing the per-field key derivation
    with a sentinel that fails on any call — the test passes only if
    the fast path returns before walking."""
    from confline.sources import env_source

    def boom(*_args, **_kwargs):
        raise AssertionError("expected fast path; _derive_key must not run")

    monkeypatch.setattr(env_source, "_derive_key", boom)

    class C(ConfigBase):
        host: str = opt("localhost")
        port: int = opt(8080)

    EnvSource({}).validate_schema(C.__config_schema__)


def test_validate_schema_runs_walk_when_underscore_in_field_name(monkeypatch):
    """Counter-example to the optimisation: an underscore in any path
    component means a collision is possible, so the walk runs. We
    observe this by counting calls to `_derive_key`."""
    from confline.sources import env_source

    calls: list[str] = []
    real = env_source._derive_key

    def spy(field, *, prefix, delimiter):
        calls.append(".".join(field.path))
        return real(field, prefix=prefix, delimiter=delimiter)

    monkeypatch.setattr(env_source, "_derive_key", spy)

    class C(ConfigBase):
        my_host: str = opt("localhost")

    EnvSource({}).validate_schema(C.__config_schema__)
    assert calls == ["my_host"]
