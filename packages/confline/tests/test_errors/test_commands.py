"""
Tests for command-dispatch errors:
- `CommandRegistrationError` (raised at decorator time)
- `UnknownCommandError` (raised when argparse rejects a subcommand)
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from confline.errors import CommandRegistrationError, UnknownCommandError

# ─────────────────────────────────────────────────────────────────────────────
# UnknownCommandError
# ─────────────────────────────────────────────────────────────────────────────


def test_unknown_command_carries_given_available_and_suggestions():
    err = UnknownCommandError(
        "migate",
        available=["migrate", "serve"],
        suggestions=["migrate"],
    )

    assert err.given == "migate"
    assert err.available == ("migrate", "serve")
    assert err.suggestions == ("migrate",)


def test_unknown_command_normalises_iterables_to_tuples():
    """The constructor accepts any `Sequence`; storing tuples keeps the
    error hashable-friendly and prevents callers from mutating it after
    raising."""
    err = UnknownCommandError("x", available=["a", "b"], suggestions=["a"])
    assert isinstance(err.available, tuple)
    assert isinstance(err.suggestions, tuple)


def test_unknown_command_message_includes_did_you_mean_when_suggestions_present():
    err = UnknownCommandError(
        "migate",
        available=["migrate", "serve"],
        suggestions=["migrate"],
    )
    msg = str(err)
    assert "unknown command: 'migate'" in msg
    assert "did you mean: migrate" in msg


def test_unknown_command_message_omits_did_you_mean_when_no_suggestions():
    """No suggestions → no parenthetical noise. The renderer adds the
    'Available commands' block separately when needed."""
    err = UnknownCommandError("migate", available=["serve"])
    msg = str(err)
    assert msg == "unknown command: 'migate'"


def test_unknown_command_accepts_none_given():
    """`given=None` covers the case of an empty argv where argparse
    can't even point at a token. The signature allows it; the message
    surfaces it as `None` rather than crashing on `.casefold()` or such."""
    err = UnknownCommandError(None, available=["serve"])
    assert err.given is None
    assert "None" in str(err)


# ─────────────────────────────────────────────────────────────────────────────
# CommandRegistrationError
# ─────────────────────────────────────────────────────────────────────────────


def test_command_registration_error_is_a_plain_config_error_subclass():
    """No structured fields by design — the message is built at the
    detection site where the conflicting names are known. The class
    exists for `except CommandRegistrationError` pattern-matching."""
    err = CommandRegistrationError("duplicate command 'serve'")
    assert str(err) == "duplicate command 'serve'"
