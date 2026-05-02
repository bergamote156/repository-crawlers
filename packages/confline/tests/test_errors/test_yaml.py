"""
Tests for YAML-source error classes:
- `YamlPathCollisionError` (schema-validation)
- `ConfigFileNotFoundError`, `YamlParseError`, `YamlSchemaError`,
  `YamlSizeLimitError` (file-load failures)
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from pathlib import Path

from confline.errors import (
    ConfigFileNotFoundError,
    YamlParseError,
    YamlPathCollisionError,
    YamlSchemaError,
    YamlSizeLimitError,
)

# ─────────────────────────────────────────────────────────────────────────────
# YamlPathCollisionError
# ─────────────────────────────────────────────────────────────────────────────


def test_yaml_path_collision_carries_path_and_both_fields():
    err = YamlPathCollisionError(path="db.host", field_a="host", field_b="legacy_host")

    assert err.path == "db.host"
    assert err.field_a == "host"
    assert err.field_b == "legacy_host"


def test_yaml_path_collision_message_lists_resolution_hints():
    """Like `EnvKeyCollisionError`, the message is the operator's
    playbook — both escape hatches (`YamlPath(...)` change, rename)
    enumerated so the schema author doesn't go grepping."""
    err = YamlPathCollisionError(path="x", field_a="a", field_b="b")
    msg = str(err)

    assert "yaml path collision" in msg
    assert "'a'" in msg and "'b'" in msg and "'x'" in msg
    assert "Resolve by:" in msg
    assert "YamlPath(" in msg
    assert "rename" in msg


# ─────────────────────────────────────────────────────────────────────────────
# ConfigFileNotFoundError
# ─────────────────────────────────────────────────────────────────────────────


def test_config_file_not_found_carries_path():
    err = ConfigFileNotFoundError(Path("/etc/app.yaml"))
    assert err.path == Path("/etc/app.yaml")
    assert err.suggestions == ()


def test_config_file_not_found_message_without_suggestions():
    err = ConfigFileNotFoundError(Path("/etc/app.yaml"))
    assert str(err) == "config file not found: /etc/app.yaml"


def test_config_file_not_found_message_with_suggestions():
    err = ConfigFileNotFoundError(
        Path("/etc/typo.yaml"),
        suggestions=["/etc/app.yaml", "/etc/api.yaml"],
    )
    msg = str(err)
    assert "config file not found: /etc/typo.yaml" in msg
    assert "did you mean: /etc/app.yaml, /etc/api.yaml" in msg


# ─────────────────────────────────────────────────────────────────────────────
# YamlParseError
# ─────────────────────────────────────────────────────────────────────────────


def test_yaml_parse_error_carries_path_line_column_and_detail():
    err = YamlParseError(
        Path("/etc/app.yaml"),
        line=12,
        column=4,
        detail="mapping values not allowed here",
    )

    assert err.path == Path("/etc/app.yaml")
    assert err.line == 12
    assert err.column == 4
    assert err.detail == "mapping values not allowed here"


def test_yaml_parse_error_message_includes_line_and_column():
    err = YamlParseError(Path("/etc/app.yaml"), line=12, column=4, detail="bad")
    assert str(err) == "YAML parse error in /etc/app.yaml:12:4 — bad"


def test_yaml_parse_error_message_with_line_only_drops_column():
    err = YamlParseError(Path("/etc/app.yaml"), line=12, detail="bad")
    assert str(err) == "YAML parse error in /etc/app.yaml:12 — bad"


def test_yaml_parse_error_message_without_location_or_detail():
    """Some PyYAML errors lack a `problem_mark` — the wrapper degrades
    to just the path so the operator at least knows which file."""
    err = YamlParseError(Path("/etc/app.yaml"))
    assert str(err) == "YAML parse error in /etc/app.yaml"


# ─────────────────────────────────────────────────────────────────────────────
# YamlSchemaError
# ─────────────────────────────────────────────────────────────────────────────


def test_yaml_schema_error_carries_path_and_reason():
    err = YamlSchemaError(Path("/etc/app.yaml"), reason="expected mapping at root, got list")
    assert err.path == Path("/etc/app.yaml")
    assert err.reason == "expected mapping at root, got list"


def test_yaml_schema_error_message_format():
    err = YamlSchemaError(Path("/etc/app.yaml"), reason="root must be a mapping")
    assert str(err) == "YAML schema error in /etc/app.yaml: root must be a mapping"


# ─────────────────────────────────────────────────────────────────────────────
# YamlSizeLimitError
# ─────────────────────────────────────────────────────────────────────────────


def test_yaml_size_limit_error_carries_path_size_and_limit():
    err = YamlSizeLimitError(Path("/etc/huge.yaml"), size=12_000_000, limit=10_485_760)
    assert err.path == Path("/etc/huge.yaml")
    assert err.size == 12_000_000
    assert err.limit == 10_485_760


def test_yaml_size_limit_error_message_format():
    err = YamlSizeLimitError(Path("/etc/huge.yaml"), size=128, limit=64)
    assert str(err) == "YAML file too large: /etc/huge.yaml is 128 bytes (limit 64)"
