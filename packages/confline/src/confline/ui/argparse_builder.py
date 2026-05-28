"""
Argparse parser builder — walks a `ConfigSchema` and emits arguments.

Two public entry points:

- `build_argparse_parser(config_class, ...)` — standalone parser for a
  single `ConfigBase` schema (used by `CliSource.from_argv` and tests
  that don't need the CommandApp dispatch layer).
- `build_command_app_parser(spec=CliSpec(...), ...)` — root parser
  with meta-flags and one subparser per registered command.

This module knows nothing about `CommandApp`; it consumes the neutral
`CliSpec` DTO from `confline.spec`.

Conventions hardcoded here:

- flag name: `"--" + ".".join(p.replace("_", "-") for p in path)`
- dest:      `".".join(path)` (dotted; argparse accepts arbitrary strings)
- default:   `argparse.SUPPRESS` on every argument so `vars(ns)` only
             holds keys the user actually passed
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import argparse
import dataclasses
import difflib
import re
from collections.abc import Callable, Sequence
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from typing import Any, Literal, get_args, get_origin
from uuid import UUID

from confline.config.base import ConfigBase
from confline.config.schema import ConfigFieldInfo, ConfigGroup, ConfigSchema
from confline.config.types import FieldPath
from confline.errors import UnknownCommandError
from confline.resolution.coerce import container_info, infer_choices
from confline.sources.base import Source
from confline.sources.cli_source import CliAlias, CliPositional, CliSource
from confline.spec import CliSpec
from confline.ui.actions import CountAction, HeterogeneousTupleAction
from confline.ui.help_format import ConflineHelpFormatter, help_text

# ─────────────────────────────────────────────────────────────────────────────
# Public entry points
# ─────────────────────────────────────────────────────────────────────────────


def build_argparse_parser(
    config_class: type[ConfigBase],
    *,
    prog: str | None = None,
    description: str | None = None,
    label_sources: Sequence[Source] = (),
) -> argparse.ArgumentParser:
    """Build an `ArgumentParser` for a single `ConfigBase` schema.

    Standalone form — emits arguments for the schema directly under
    the root parser.

    `label_sources` is consumed by `ConflineHelpFormatter` via
    `describe_field` to render the per-option block (env var, yaml
    path, etc.). Pass empty for help that shows only default and tags.
    """
    parser = _make_parser(prog, description, label_sources)
    _emit_schema_args(parser, config_class.__config_schema__)
    return parser


def build_command_app_parser(
    *,
    spec: CliSpec,
    label_sources: Sequence[Source] = (),
) -> argparse.ArgumentParser:
    """Build an `ArgumentParser` for a CommandApp `spec`.

    Emits root meta-flags (e.g. `-c/--config`) and one subparser per
    registered command, each populated with that command's
    `config_class` schema.
    """
    parser = _make_parser(spec.prog, spec.description, label_sources)
    _emit_meta_flags(parser, spec)
    _emit_subparsers(parser, spec, label_sources)
    return parser


# ─────────────────────────────────────────────────────────────────────────────
# Parser construction — factory + custom subclass
# ─────────────────────────────────────────────────────────────────────────────


def _make_parser(
    prog: str | None,
    description: str | None,
    label_sources: Sequence[Source],
) -> "_ConflineArgumentParser":
    """Construct the root `_ConflineArgumentParser` with our formatter.

    Stamps `_confline_formatter_class` on the parser so subparsers can
    inherit the same formatter — argparse won't propagate `formatter_class`
    to children on its own.
    """
    formatter_cls = _make_formatter_class(label_sources)
    parser = _ConflineArgumentParser(
        prog=prog,
        description=description,
        formatter_class=formatter_cls,
    )
    parser._confline_formatter_class = formatter_cls  # type: ignore[attr-defined]
    return parser


def _make_formatter_class(
    label_sources: Sequence[Source],
) -> type[ConflineHelpFormatter]:
    """Build a `ConflineHelpFormatter` subclass with `label_sources` baked in.

    Argparse instantiates the formatter itself per-render using the
    `(prog,)` constructor, which leaves no other clean way to inject
    extra context — a closure subclass is the least-invasive seam.
    """
    sources_tuple = tuple(label_sources)

    class _Formatter(ConflineHelpFormatter):
        label_sources = sources_tuple

    _Formatter.__name__ = "_ConflineHelpFormatterWithSources"
    return _Formatter


_INVALID_CHOICE_RE = re.compile(
    r"argument _command: invalid choice: '(?P<given>[^']+)'",
)


class _ConflineArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that promotes argparse's "invalid choice"
    subcommand error into a typed `UnknownCommandError` with did-you-
    mean suggestions.

    `_emit_subparsers` stamps `_confline_commands` with the canonical
    command name list; without it the parser behaves like the stock
    `ArgumentParser`. Matching argparse's English error string is
    fragile by design — argparse provides no structured hook for
    intercepting this specific case.
    """

    _confline_commands: tuple[str, ...] = ()

    def error(self, message: str) -> None:  # type: ignore[override]
        match = _INVALID_CHOICE_RE.search(message)
        if match and self._confline_commands:
            given = match.group("given")
            suggestions = difflib.get_close_matches(
                given,
                self._confline_commands,
                n=3,
                cutoff=0.6,
            )
            raise UnknownCommandError(
                given,
                available=self._confline_commands,
                suggestions=suggestions,
            )
        super().error(message)


# ─────────────────────────────────────────────────────────────────────────────
# CommandApp emission — root meta-flags + subparser per command
# ─────────────────────────────────────────────────────────────────────────────


def _emit_meta_flags(
    parser: argparse.ArgumentParser,
    spec: CliSpec,
) -> None:
    """Add CommandApp-level flags (`-c/--config`, etc.) at the root."""
    if spec.config_option:
        parser.add_argument(
            *spec.config_option,
            dest="_config_files",
            action="append",
            type=Path,
            default=argparse.SUPPRESS,
            metavar="FILE",
            help="Load YAML config (repeatable; later files win on overlap).",
        )


def _emit_subparsers(
    parser: argparse.ArgumentParser,
    spec: CliSpec,
    label_sources: Sequence[Source],  # noqa: ARG001 — reserved for future per-subparser overrides
) -> None:
    """Emit one subparser per command in `spec.commands`.

    Stamps `_confline_commands` on the root so `_ConflineArgumentParser.error`
    can promote argparse's "invalid choice" into `UnknownCommandError`.
    """
    formatter_cls = getattr(parser, "_confline_formatter_class", None)
    inherited_epilog = _build_inherited_epilog(spec)

    if isinstance(parser, _ConflineArgumentParser):
        parser._confline_commands = tuple(spec.commands.keys())

    # `required=False` so bare `myapp` doesn't trigger argparse's
    # "the following arguments are required: {_command}" — `CommandApp.run`
    # handles the no-command case by printing top-level help and returning 0.
    subparsers = parser.add_subparsers(dest="_command", required=False)
    for cmd in spec.commands.values():
        kwargs = _build_subparser_kwargs(cmd, formatter_cls, inherited_epilog)
        sub = subparsers.add_parser(cmd.name, **kwargs)
        _emit_schema_args(sub, cmd.config_class.__config_schema__)


def _build_subparser_kwargs(
    cmd: Any,
    formatter_cls: type[ConflineHelpFormatter] | None,
    inherited_epilog: str,
) -> dict[str, Any]:
    """Build the kwargs passed to `subparsers.add_parser` for one command."""
    kwargs: dict[str, Any] = {"aliases": list(cmd.aliases)}
    if cmd.description:
        # `help` shows in the parent parser's subcommands listing;
        # `description` shows at the top of `myapp <cmd> --help`. Same
        # one-liner serves both.
        kwargs["help"] = cmd.description
        kwargs["description"] = cmd.description
    if formatter_cls is not None:
        kwargs["formatter_class"] = formatter_cls
    if inherited_epilog:
        kwargs["epilog"] = inherited_epilog
    return kwargs


def _build_inherited_epilog(spec: CliSpec) -> str:
    """Text-only mirror of root-level meta-flags for subparser help.

    Argparse hides root flags from subparser `--help` since they belong
    to a different scope. The epilog re-surfaces them so users see
    `-c/--config` exists without scrolling back to `<prog> --help`.
    """
    if not spec.config_option:
        return ""
    flag_str = ", ".join(spec.config_option)
    return (
        f"Inherited from root:\n  {flag_str} FILE   Load YAML config (repeatable; later files win)."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Schema → argparse arguments
# ─────────────────────────────────────────────────────────────────────────────


def _emit_schema_args(
    root_parser: argparse.ArgumentParser,
    schema: ConfigSchema,
    *,
    prefix: FieldPath = (),
) -> None:
    """Emit one argument_group per `ConfigGroup`, attached to the root.

    Argparse deprecated nesting argument groups; nested config classes
    get their own top-level argument_group whose title carries the
    dotted prefix instead.
    """
    for group in schema.groups:
        _emit_group(root_parser, group, prefix=prefix)


def _emit_group(
    root_parser: argparse.ArgumentParser,
    group: ConfigGroup,
    *,
    prefix: FieldPath = (),
) -> None:
    """Emit one `ConfigGroup` — plain argument_group or mutex group."""
    title = group.name
    if prefix:
        title = f"{'.'.join(prefix)} ({group.name})"
    ag = root_parser.add_argument_group(
        title=title,
        description=group.description,
    )

    if not group.is_mutex:
        for field in group.fields:
            _emit_field(root_parser, ag, field, prefix=prefix)
        return

    # Argparse's `required=` only sees CLI flags — confline must also
    # accept "satisfied by YAML/ENV" so we leave argparse permissive
    # and run the full required/exclusive check post-resolution
    # against per-field provenance.
    mutex = ag.add_mutually_exclusive_group(required=False)
    for field in group.fields:
        action = _emit_field(root_parser, mutex, field, prefix=prefix)
        if action is not None:
            _stamp_mutex_metadata(action, group)


def _emit_field(
    root_parser: argparse.ArgumentParser,
    target: argparse._ArgumentGroup | argparse._MutuallyExclusiveGroup,
    field: ConfigFieldInfo,
    *,
    prefix: FieldPath = (),
) -> argparse.Action | None:
    """Emit one field's argument(s).

    Returns the created action so callers can stamp extra metadata
    onto it (mutex group name, etc.). Returns `None` for fields
    excluded from the CLI, unsupported by `CliSource`, nested
    `ConfigBase` (recursed into as fresh argument_groups), and nested
    positionals (out of scope — see inline note).
    """
    if CliSource in field.excluded_from:
        return None
    if not CliSource.supports_field(field):
        return None

    full_path = prefix + field.path

    if field.nested_schema is not None:
        # Nested ConfigBase — emit each sub-group as a fresh top-level
        # argument_group on the root parser, prefixed with the field path.
        for sub_group in field.nested_schema.groups:
            _emit_group(root_parser, sub_group, prefix=full_path)
        return None

    is_positional = _is_positional(field)
    if is_positional and len(full_path) > 1:
        # Nested positionals are not in scope for Block 2 — they
        # require special dest handling argparse doesn't support cleanly.
        return None

    if is_positional:
        action = _emit_positional(target, field, full_path)
    else:
        action = _emit_flag(target, field, full_path)

    _stamp_field_metadata(action, field, full_path)
    return action


_RESERVED_DESTS = frozenset({"_command", "_config_files"})


def _emit_flag(
    target: Any,
    field: ConfigFieldInfo,
    full_path: FieldPath,
) -> argparse.Action:
    """Emit a `--name` (or aliased) optional argument for `field`."""
    flag_names = _flag_names(field, full_path)
    kwargs = _argparse_kwargs(field, full_path)

    dest = ".".join(full_path)
    if dest in _RESERVED_DESTS:
        raise ValueError(
            f"field path {full_path!r} produces reserved CLI dest "
            f"{dest!r} — confline uses this for the meta-flag namespace. "
            "Rename the field or set excluded_from=[CliSource].",
        )
    kwargs["dest"] = dest
    kwargs["default"] = argparse.SUPPRESS
    return target.add_argument(*flag_names, **kwargs)


def _emit_positional(
    target: Any,
    field: ConfigFieldInfo,
    full_path: FieldPath,
) -> argparse.Action:
    """Emit a positional argument for `field`."""
    aliases = _last_alias(field)
    name = aliases[0] if aliases else field.name
    kwargs = _argparse_kwargs(field, full_path)
    kwargs.pop("dest", None)
    kwargs["default"] = argparse.SUPPRESS
    if field.has_default:
        kwargs.setdefault("nargs", "?")
    return target.add_argument(name, **kwargs)


def _stamp_field_metadata(
    action: argparse.Action,
    field: ConfigFieldInfo,
    full_path: FieldPath,
) -> None:
    """Attach the field info that `ConflineHelpFormatter` reads at render time.

    Replaces `path` with `full_path` so source-key derivation
    (`MYAPP_BIND__PORT`, `db.host`) sees the dotted composition at
    help/error time, not the leaf-relative path.
    """
    action._confline_field = dataclasses.replace(field, path=full_path)  # type: ignore[attr-defined]


def _stamp_mutex_metadata(action: argparse.Action, group: ConfigGroup) -> None:
    """Attach mutex group info that `ConflineHelpFormatter` reads to render
    `[mutex: <group>]` and decide whether `[active by default]` applies.

    The sibling list lets the formatter check whether *this* field
    uniquely owns the default in the group — without it, both sides
    of a two-default group would falsely advertise "active by default".
    """
    action._confline_mutex_group = group.name  # type: ignore[attr-defined]
    action._confline_mutex_group_fields = tuple(group.fields)  # type: ignore[attr-defined]


# ─────────────────────────────────────────────────────────────────────────────
# Per-field argparse kwargs — type, action, choices, metavar
# ─────────────────────────────────────────────────────────────────────────────


def _argparse_kwargs(
    field: ConfigFieldInfo,
    full_path: FieldPath,
) -> dict[str, Any]:
    """Build the argparse kwargs for a leaf field.

    Dispatch order: `is_count` → `bool` → container → scalar. Each
    branch finalises the dict and returns; only one shape applies.
    """
    kwargs: dict[str, Any] = {"help": help_text(field)}

    metavar = _metavar_for(field, full_path)
    if metavar is not None:
        kwargs["metavar"] = metavar

    if field.is_count:
        kwargs["action"] = CountAction
        return kwargs

    if field.field_type is bool:
        kwargs["action"] = argparse.BooleanOptionalAction
        return kwargs

    container_origin, type_args = container_info(field.field_type)
    if container_origin is not None:
        _populate_container_kwargs(kwargs, container_origin, type_args, field)
    else:
        _populate_scalar_kwargs(kwargs, field)
    return kwargs


def _metavar_for(field: ConfigFieldInfo, full_path: FieldPath) -> str | None:
    """Decide the argparse `metavar` for a field.

    Explicit `field.metavar` wins. Otherwise, nested fields get the
    last path segment uppercased (`--db.url URL` reads as a value
    name; the auto-derived `DB.URL` looked like a typo).
    """
    if field.metavar is not None:
        return field.metavar
    if len(full_path) > 1:
        return full_path[-1].upper()
    return None


def _populate_container_kwargs(
    kwargs: dict[str, Any],
    origin: type,
    type_args: tuple[Any, ...],
    field: ConfigFieldInfo,
) -> None:
    """Fill `kwargs` for `list[X]`, `set[X]`, `frozenset[X]`, `tuple[...]`."""
    if origin is list:
        item_type = type_args[0] if type_args else str
        kwargs["action"] = "append"
        kwargs["type"] = _scalar_type_callable(item_type) or str
        choices = field.choices if field.choices is not None else infer_choices(item_type)
        if choices is not None:
            kwargs["choices"] = list(choices)
        return

    if origin in (set, frozenset):
        item_type = type_args[0] if type_args else str
        kwargs["action"] = "append"
        kwargs["type"] = _scalar_type_callable(item_type) or str
        return

    if origin is tuple:
        _VARIADIC_ARITY = 2
        if len(type_args) == _VARIADIC_ARITY and type_args[1] is Ellipsis:
            item_type = type_args[0]
            kwargs["nargs"] = "*"
            kwargs["type"] = _scalar_type_callable(item_type) or str
            return
        # Heterogeneous — per-position parsing via HeterogeneousTupleAction.
        kwargs["nargs"] = len(type_args)
        kwargs["action"] = HeterogeneousTupleAction
        kwargs["types"] = tuple(_scalar_type_callable(t) or str for t in type_args)


def _populate_scalar_kwargs(
    kwargs: dict[str, Any],
    field: ConfigFieldInfo,
) -> None:
    """Fill `kwargs` for a plain scalar field — `type=` and `choices=`."""
    type_callable = _scalar_type_callable(field.field_type)
    if type_callable is not None:
        kwargs["type"] = type_callable

    choices = field.choices if field.choices is not None else infer_choices(field.field_type)
    if choices is not None:
        kwargs["choices"] = list(choices)


# ─────────────────────────────────────────────────────────────────────────────
# Type → callable dispatch — picks the parser argparse should use as `type=`
# ─────────────────────────────────────────────────────────────────────────────


# Built-in scalar types whose constructor or classmethod doubles as a
# `str -> value` parser. Order doesn't matter — lookup is by identity.
_SCALAR_TYPE_PARSERS: dict[type, Callable[[str], Any]] = {
    str: str,
    int: int,
    float: float,
    Path: Path,
    UUID: UUID,
    datetime: datetime.fromisoformat,
    date: date.fromisoformat,
    time: time.fromisoformat,
}


def _scalar_type_callable(target: type) -> Callable[[str], Any] | None:
    """Return the callable argparse should use as `type=` for a scalar.

    Returns `None` when the type isn't recognised — caller decides
    whether to fall back to `str` or skip `type=` entirely.
    """
    # `Any` collapses to `str` — argparse stores the raw input verbatim.
    if target is Any:
        return str

    parser = _SCALAR_TYPE_PARSERS.get(target)
    if parser is not None:
        return parser

    if isinstance(target, type) and issubclass(target, Enum):
        return _enum_parser(target)

    if get_origin(target) is Literal:
        return _literal_type_callable(target)

    # Last-resort hook: classes opt in to custom parsing by defining
    # `__confline_convert__` as a classmethod or staticmethod.
    if isinstance(target, type):
        convert = getattr(target, "__confline_convert__", None)
        if convert is not None:
            return convert  # type: ignore[return-value]

    return None


def _literal_type_callable(target: type) -> Callable[[str], Any]:
    """Return the `type=` callable for a `Literal[...]` annotation.

    Argparse validates the parsed value against `choices=` separately;
    this callable just coerces the raw string into the right primitive
    so `Literal[1, 2]` and `Literal[1.0, 2.0]` match by value rather
    than by string. Mixed/non-numeric literals fall back to `str`.
    """
    members = get_args(target)
    inner_types = {type(m) for m in members if m is not None}
    if len(inner_types) == 1:
        inner = inner_types.pop()
        if inner in (int, float):
            return inner  # type: ignore[return-value]
    return str


def _enum_parser(enum_cls: type[Enum]) -> Callable[[str], Enum]:
    """Argparse `type=` callable for an Enum — by-value first, by-name fallback."""

    def parse(raw: str) -> Enum:
        try:
            return enum_cls(raw)
        except ValueError:
            pass
        try:
            return enum_cls[raw]
        except KeyError as exc:
            raise argparse.ArgumentTypeError(
                f"{raw!r} is not a valid {enum_cls.__name__}",
            ) from exc

    return parse


# ─────────────────────────────────────────────────────────────────────────────
# Naming + Annotated metadata helpers
# ─────────────────────────────────────────────────────────────────────────────


def _flag_names(field: ConfigFieldInfo, full_path: FieldPath) -> tuple[str, ...]:
    """Return the flag spellings for `field` — last `CliAlias` wins, else auto."""
    aliases = _last_alias(field)
    if aliases:
        return aliases
    return ("--" + ".".join(p.replace("_", "-") for p in full_path),)


def _last_alias(field: ConfigFieldInfo) -> tuple[str, ...]:
    """Return the last `CliAlias` names tuple in the field's annotations.

    Last-wins per the A2 Annotated discovery rules.
    """
    last: tuple[str, ...] = ()
    for m in field.annotated:
        if isinstance(m, CliAlias):
            last = m.names
    return last


def _is_positional(field: ConfigFieldInfo) -> bool:
    """True when `CliPositional` appears in the field's annotations."""
    return any(
        m is CliPositional or (isinstance(m, type) and issubclass(m, CliPositional))
        for m in field.annotated
    )
