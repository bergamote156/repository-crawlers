"""
Tests for `YamlSource`, `YamlPath`, and the on-disk file factory
`YamlSource.from_files`.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import dataclasses
from typing import Annotated

import pytest
import yaml

from confline.config.base import ConfigBase
from confline.config.schema import opt
from confline.errors import (
    ConfigFileNotFoundError,
    YamlParseError,
    YamlPathCollisionError,
    YamlSchemaError,
    YamlSizeLimitError,
)
from confline.sources.base import NO_VALUE
from confline.sources.yaml_source import YamlPath, YamlSource


class _Cfg(ConfigBase):
    host: str = opt("localhost")
    api_key: Annotated[str, YamlPath("creds", "key")] = opt("default")
    no_yaml: str = opt("default", excluded_from=[YamlSource])


def _f(name: str):
    return _Cfg.__config_schema__.find_field(name)


# ─────────────────────────────────────────────────────────────────────────────
# YamlPath marker
# ─────────────────────────────────────────────────────────────────────────────


def test_yaml_path_requires_at_least_one_part():
    with pytest.raises(ValueError, match="at least one part"):
        YamlPath()


def test_yaml_path_equality_and_hash_are_value_based():
    """Hand-written rather than `@dataclass(frozen=True)` — the `*parts`
    constructor matters more than dataclass boilerplate. Equality/hash
    must still behave as a value type."""
    a = YamlPath("creds", "key")
    b = YamlPath("creds", "key")
    c = YamlPath("creds")

    assert a == b
    assert hash(a) == hash(b)
    assert a != c
    assert a != "YamlPath('creds', 'key')"


def test_yaml_path_repr_lists_parts():
    assert repr(YamlPath("creds", "key")) == "YamlPath('creds', 'key')"


# ─────────────────────────────────────────────────────────────────────────────
# resolve()
# ─────────────────────────────────────────────────────────────────────────────


def test_resolves_top_level_key():
    src = YamlSource(scopes=[{"host": "yaml-host"}])
    assert src.resolve(_f("host")) == "yaml-host"


def test_returns_no_value_for_absent_key():
    src = YamlSource(scopes=[{}])
    assert src.resolve(_f("host")) is NO_VALUE


def test_yaml_null_returns_real_none():
    """`host: null` in YAML is an explicit value; only an *absent* key
    falls through to the next scope or source."""
    src = YamlSource(scopes=[{"host": None}])
    assert src.resolve(_f("host")) is None


def test_yaml_path_marker_overrides_dict_walk():
    src = YamlSource(scopes=[{"creds": {"key": "secret"}}])
    assert src.resolve(_f("api_key")) == "secret"


def test_higher_priority_scope_wins():
    src = YamlSource(scopes=[
        {"host": "high"},
        {"host": "low"},
    ])
    assert src.resolve(_f("host")) == "high"


def test_lower_priority_fills_missing_key():
    src = YamlSource(scopes=[
        {},
        {"host": "fallback"},
    ])
    assert src.resolve(_f("host")) == "fallback"


def test_nested_walk_for_full_path():
    f = dataclasses.replace(_f("host"), path=("db", "host"))
    src = YamlSource(scopes=[{"db": {"host": "nested"}}])
    assert src.resolve(f) == "nested"


def test_walk_short_circuits_on_non_mapping_intermediate():
    """If an intermediate path component is not a mapping (e.g. the
    user wrote `db: 5` when the schema expects a nested config), the
    walk returns NO_VALUE rather than crashing."""
    f = dataclasses.replace(_f("host"), path=("db", "host"))
    src = YamlSource(scopes=[{"db": 5}])
    assert src.resolve(f) is NO_VALUE


# ─────────────────────────────────────────────────────────────────────────────
# supports_field — YAML carries every shape natively
# ─────────────────────────────────────────────────────────────────────────────


def test_supports_field_accepts_list_of_config_base():
    """Argparse and env self-skip `list[ConfigBase]`; YAML must accept
    it because that's the shape's natural home."""

    class Item(ConfigBase):
        name: str = opt("x")

    class Cfg(ConfigBase):
        items: list[Item] = opt(default_factory=list)

    items = Cfg.__config_schema__.find_field("items")
    assert YamlSource.supports_field(items) is True


# ─────────────────────────────────────────────────────────────────────────────
# from_files() factory
# ─────────────────────────────────────────────────────────────────────────────


def test_from_files_resolves_per_field_with_last_wins(tmp_path):
    """Each file becomes its own scope; later files in the input
    sequence override earlier ones at the leaf level. Equivalent leaf
    semantics to the old deep-merge, with per-file provenance as the
    gain."""
    base = tmp_path / "base.yaml"
    base.write_text("db:\n  host: base-host\n  port: 5432\n", encoding="utf-8")
    override = tmp_path / "override.yaml"
    override.write_text("db:\n  host: override-host\nworkers: 8\n", encoding="utf-8")

    src = YamlSource.from_files([base, override])

    db_host = dataclasses.replace(_f("host"), path=("db", "host"))
    db_port = dataclasses.replace(_f("host"), path=("db", "port"))
    workers = dataclasses.replace(_f("host"), path=("workers",))

    assert src.resolve(db_host) == "override-host"
    assert src.resolve(db_port) == 5432
    assert src.resolve(workers) == 8


def test_from_files_raises_on_missing_path(tmp_path):
    """Silent skip on missing files masks `--config /etc/typo.yaml` —
    the error must be hard so a typo cannot quietly fall through to
    defaults."""
    missing = tmp_path / "missing.yaml"
    with pytest.raises(ConfigFileNotFoundError) as exc:
        YamlSource.from_files([missing])
    assert exc.value.path == missing


def test_from_files_accepts_empty_yaml_as_no_overrides(tmp_path):
    """`yaml.safe_load` returns None for an empty file — that's a no-op,
    not an error. Subsequent files merge normally."""
    empty = tmp_path / "empty.yaml"
    empty.write_text("", encoding="utf-8")
    real = tmp_path / "ok.yaml"
    real.write_text("host: real\n", encoding="utf-8")

    src = YamlSource.from_files([empty, real])
    assert src.resolve(_f("host")) == "real"


def test_from_files_rejects_non_mapping_root(tmp_path):
    """A list at the root is almost always a hand-edit mistake; reject
    loudly with the path so the operator can see which file is wrong."""
    not_a_dict = tmp_path / "list.yaml"
    not_a_dict.write_text("- 1\n- 2\n", encoding="utf-8")

    with pytest.raises(YamlSchemaError) as exc:
        YamlSource.from_files([not_a_dict])
    assert exc.value.path == not_a_dict
    assert "list" in exc.value.reason


def test_from_files_wraps_yaml_parse_error_with_path_and_line(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("host: localhost\n  port: 8080\n", encoding="utf-8")

    with pytest.raises(YamlParseError) as exc:
        YamlSource.from_files([bad])
    assert exc.value.path == bad
    assert exc.value.line is not None
    assert isinstance(exc.value.__cause__, yaml.YAMLError)


def test_from_files_enforces_size_limit(tmp_path, monkeypatch):
    """First-line DoS guard — refuse to parse files larger than
    `MAX_FILE_BYTES`, preventing a wandering operator from feeding the
    process a 10 GB log file."""
    monkeypatch.setattr(YamlSource, "MAX_FILE_BYTES", 16)
    huge = tmp_path / "huge.yaml"
    huge.write_text("host: " + "x" * 64 + "\n", encoding="utf-8")

    with pytest.raises(YamlSizeLimitError) as exc:
        YamlSource.from_files([huge])
    assert exc.value.path == huge
    assert exc.value.limit == 16


# ─────────────────────────────────────────────────────────────────────────────
# describe_field()
# ─────────────────────────────────────────────────────────────────────────────


def test_describe_field_returns_dotted_path():
    src = YamlSource(scopes=[])
    assert src.describe_field(_f("host")) == "host"


def test_describe_field_honors_yaml_path_marker():
    src = YamlSource(scopes=[])
    assert src.describe_field(_f("api_key")) == "creds.key"


def test_describe_field_returns_none_when_excluded():
    src = YamlSource(scopes=[])
    assert src.describe_field(_f("no_yaml")) is None


# ─────────────────────────────────────────────────────────────────────────────
# describe_provenance()
# ─────────────────────────────────────────────────────────────────────────────


def test_describe_provenance_returns_none_for_in_memory_source():
    """In-memory `YamlSource` has no file origin per scope, so
    provenance returns None and the renderer falls back to
    `display_label = "yaml"`."""
    src = YamlSource(scopes=[{}])
    assert src.describe_provenance(_f("host")) is None


def test_describe_provenance_includes_path_when_built_from_file(tmp_path):
    cfg = tmp_path / "app.yaml"
    cfg.write_text("host: x\n", encoding="utf-8")

    src = YamlSource.from_files([cfg])
    label = src.describe_provenance(_f("host"))

    assert label == f"yaml {cfg}"


def test_describe_provenance_names_winning_file_for_multi_file(tmp_path):
    """With multiple files, provenance names the actual file that
    supplied the field — not the merged set. Last input file wins, so
    when both files set `host`, the label points at the later file."""
    a = tmp_path / "a.yaml"
    a.write_text("host: x\n", encoding="utf-8")
    b = tmp_path / "b.yaml"
    b.write_text("host: y\n", encoding="utf-8")
    src = YamlSource.from_files([a, b])

    label = src.describe_provenance(_f("host"))
    assert label == f"yaml {b}"


def test_describe_provenance_falls_through_to_lower_priority_file(tmp_path):
    """When the higher-priority file lacks a key, provenance points at
    the lower-priority file that actually supplied it."""
    a = tmp_path / "a.yaml"
    a.write_text("host: x\n", encoding="utf-8")
    b = tmp_path / "b.yaml"
    b.write_text("api_key: secret\n", encoding="utf-8")
    src = YamlSource.from_files([a, b])

    assert src.describe_provenance(_f("host")) == f"yaml {a}"


# ─────────────────────────────────────────────────────────────────────────────
# describe_unset_hint()
# ─────────────────────────────────────────────────────────────────────────────


def test_unset_hint_names_yaml_key():
    assert YamlSource(scopes=[]).describe_unset_hint("output.path") == (
        " — remove output.path"
    )


# ─────────────────────────────────────────────────────────────────────────────
# validate_schema() — YamlPath collision detection
# ─────────────────────────────────────────────────────────────────────────────


def test_validate_schema_detects_yaml_path_collision():
    class C(ConfigBase):
        host: str = opt("localhost")
        legacy_host: Annotated[str, YamlPath("host")] = opt("localhost")

    with pytest.raises(YamlPathCollisionError) as exc:
        YamlSource(scopes=[]).validate_schema(C.__config_schema__)

    err = exc.value
    assert err.path == "host"
    assert {err.field_a, err.field_b} == {"host", "legacy_host"}


def test_validate_schema_ignores_yaml_excluded_field():
    """A field excluded from YAML resolution can carry a `YamlPath`
    that nominally collides — validation must skip it because the
    field is not addressable through this source."""
    class C(ConfigBase):
        host: str = opt("localhost")
        legacy_host: Annotated[str, YamlPath("host")] = opt(
            "localhost", excluded_from=[YamlSource],
        )

    YamlSource(scopes=[]).validate_schema(C.__config_schema__)
