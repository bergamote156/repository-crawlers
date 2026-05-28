"""
Tests for the `ConfigError` root and the `_EXIT_CODE` ClassVar contract.

Each subclass declares an exit code matched to a sysexits role
(`man sysexits`). The contract is observable two ways:

- structurally on the class (this file), so a missing override fails
  fast even if no end-to-end run happens to hit that error;
- behaviourally via `CommandApp.run` mapping it to `SystemExit.code`
  (see `tests/test_ui/test_errors.py`).
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import pytest

from confline.errors import (
    CommandRegistrationError,
    ConfigError,
    ConfigFileNotFoundError,
    EnvKeyCollisionError,
    MissingRequiredError,
    MutexViolationError,
    SourceValueError,
    UnknownCommandError,
    YamlParseError,
    YamlPathCollisionError,
    YamlSchemaError,
    YamlSizeLimitError,
)

# ─────────────────────────────────────────────────────────────────────────────
# Hierarchy
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "cls",
    [
        SourceValueError,
        MissingRequiredError,
        MutexViolationError,
        CommandRegistrationError,
        UnknownCommandError,
        EnvKeyCollisionError,
        ConfigFileNotFoundError,
        YamlPathCollisionError,
        YamlParseError,
        YamlSchemaError,
        YamlSizeLimitError,
    ],
)
def test_every_confline_error_subclasses_config_error(cls):
    """All confline errors share `ConfigError` as their root so handlers
    can `except ConfigError` without enumerating subclasses."""
    assert issubclass(cls, ConfigError)


def test_config_error_subclasses_exception():
    assert issubclass(ConfigError, Exception)


# ─────────────────────────────────────────────────────────────────────────────
# Exit-code convention (sysexits)
# ─────────────────────────────────────────────────────────────────────────────


def test_config_error_default_exit_code_is_ex_config():
    """Unknown `ConfigError` subclasses fall back to 78 (EX_CONFIG) —
    treated as configuration problems, not transient — so a missing
    override doesn't degrade to a generic 1."""
    assert ConfigError._EXIT_CODE == 78


@pytest.mark.parametrize(
    ("cls", "code", "role"),
    [
        # EX_USAGE — operator input error.
        (UnknownCommandError, 64, "EX_USAGE"),
        (MissingRequiredError, 64, "EX_USAGE"),
        (MutexViolationError, 64, "EX_USAGE"),
        # EX_DATAERR — input data malformed.
        (SourceValueError, 65, "EX_DATAERR"),
        (YamlParseError, 65, "EX_DATAERR"),
        (YamlSchemaError, 65, "EX_DATAERR"),
        (YamlSizeLimitError, 65, "EX_DATAERR"),
        # EX_NOINPUT — input file missing.
        (ConfigFileNotFoundError, 66, "EX_NOINPUT"),
    ],
)
def test_subclasses_override_exit_code_to_match_sysexits_role(cls, code, role):
    assert code == cls._EXIT_CODE, f"{cls.__name__} should map to {role}"


@pytest.mark.parametrize(
    "cls",
    [
        EnvKeyCollisionError,
        YamlPathCollisionError,
        CommandRegistrationError,
    ],
)
def test_framework_misconfig_subclasses_inherit_default_exit_code(cls):
    """Schema-author/framework misconfigurations don't override
    `_EXIT_CODE` — they're configuration errors proper, mapped to 78
    (EX_CONFIG) by the base class."""
    assert cls._EXIT_CODE == 78
