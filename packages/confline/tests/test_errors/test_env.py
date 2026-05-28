"""
Tests for `EnvKeyCollisionError` — raised by `EnvSource.validate_schema`
when two fields would derive the same env-var name.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from confline.errors import EnvKeyCollisionError


def test_carries_key_and_both_field_paths():
    err = EnvKeyCollisionError(key="FOO_BAR", field_a="foo_bar", field_b="foo.bar")

    assert err.source_native_key == "FOO_BAR"
    assert err.field_a == "foo_bar"
    assert err.field_b == "foo.bar"


def test_message_names_both_fields_and_the_colliding_key():
    err = EnvKeyCollisionError(key="FOO_BAR", field_a="foo_bar", field_b="foo.bar")
    msg = str(err)

    assert "'foo_bar'" in msg
    assert "'foo.bar'" in msg
    assert "'FOO_BAR'" in msg
    assert "env var name collision" in msg


def test_message_includes_resolution_hints():
    """The error is raised at schema-validation time, so the message
    doubles as the operator's playbook — listing every escape hatch
    (`delimiter=...`, `EnvAlias`, rename) so they don't have to grep
    docs while the build is broken."""
    err = EnvKeyCollisionError(key="X", field_a="a", field_b="b")
    msg = str(err)

    assert "Resolve by:" in msg
    assert "EnvSource(delimiter=" in msg
    assert "EnvAlias(" in msg
    assert "rename" in msg
