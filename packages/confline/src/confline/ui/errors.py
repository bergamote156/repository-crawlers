"""
Rendering templates for confline errors.

`render_for_cli(error, ...)` is the single entry point used by
`CommandApp` to turn a `ConfigError` into an operator-facing stderr
message. Per-error templates (`format_value_error`,
`format_mutex_error`, etc.) are pure functions returning
`rich.text.Text` — every input comes through the error's frozen
dataclass fields plus optional `label_sources` for cross-source hints.

`Text` is the return type so the rendering can carry style information
into a `Console.print(...)` call (CommandApp respects `NO_COLOR` and
non-tty stderr automatically). Substring assertions in tests still
work — `Text.__contains__` reads `Text.plain`.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from collections.abc import Sequence

from rich.text import Text

from confline.errors import (
    ConfigError,
    MissingRequiredError,
    MutexViolationError,
    ProvidedField,
    SourceValueError,
    SourceValueRecord,
    UnknownCommandError,
)
from confline.sources.base import Source

# ─────────────────────────────────────────────────────────────────────────────
# Top-level dispatch — single seam called by CommandApp
# ─────────────────────────────────────────────────────────────────────────────


def render_for_cli(
    error: ConfigError,
    *,
    prog: str | None = None,
    command: str | None = None,
    label_sources: Sequence[Source] = (),
) -> Text:
    """Render a `ConfigError` for stderr.

    Closed dispatch — every error type confline raises has a known
    template; unknown types fall through to a single-line `prog: msg`
    fallback. Confline does not support external `ConfigError`
    subclasses with custom rendering — the renderer lives where the
    templates live, not on the exception class.
    """
    match error:
        case SourceValueError() if error.field_record is not None:
            return format_value_error(
                error.field_record,
                detail=error.detail,
                prog=prog,
                command=command,
            )
        case MissingRequiredError():
            return format_missing_required(
                error, prog=prog, command=command, label_sources=label_sources,
            )
        case MutexViolationError():
            return format_mutex_error(
                error, prog=prog, command=command, label_sources=label_sources,
            )
        case UnknownCommandError():
            return format_unknown_command(error, prog=prog)
        case _:
            return _header_line(prog, command, str(error), error_style="default")


# ─────────────────────────────────────────────────────────────────────────────
# Theme — palette aligned with `help_format` and rich-argparse defaults
# ─────────────────────────────────────────────────────────────────────────────


# Section headers (`Try one of:`, `Did you mean:`, `Available commands:`)
# borrow `argparse.groups` styling — operators see the same orange cue
# that marks `positional arguments:` / `options:` in `--help`.
_SECTION_HEADER_STYLE = "dark_orange"

# Items listed under section headers (suggestion lines, command names)
# borrow `argparse.args` cyan — same colour `--port` / `-h` carry in help.
_ITEM_STYLE = "cyan"

# Per-source key colours match `help_format` (env=yellow, yaml=magenta).
_SOURCE_KEY_STYLES: dict[str, str] = {
    "argparse": "cyan",
    "env": "yellow",
    "yaml": "magenta",
}


def _source_key_style(source_name: str) -> str:
    """Style for an in-line `--port` / `MYAPP_X` / `port:` key fragment."""
    return _SOURCE_KEY_STYLES.get(source_name, "default")


def _section_header(label: str) -> Text:
    """Render a help-section header inside an error body.

    Style matches `argparse.groups` in help output so operators see the
    same visual cue across help and error surfaces.
    """
    return Text(label, style=_SECTION_HEADER_STYLE)


def _item_line(text: str) -> Text:
    """Render one listed item under a section header — `argparse.args` cyan."""
    return Text(text, style=_ITEM_STYLE)


# ─────────────────────────────────────────────────────────────────────────────
# Building blocks — header, body row, footer, line joiner
# ─────────────────────────────────────────────────────────────────────────────


_BODY_LABEL_WIDTH = 10  # `expected:` is the widest body label.


def _header_line(
    prog: str | None,
    command: str | None,
    message: str,
    *,
    error_style: str = "bold red",
) -> Text:
    """Render `prog command: <message>` — prefix bold, message coloured.

    The prefix is dropped when both `prog` and `command` are absent
    (matching the legacy string template). `error_style` defaults to
    `bold red` so the eye lands on the failure summary first; the
    fallback path passes `default` for the generic "unknown error"
    case where the message is just `str(error)`.
    """
    prefix_parts = [p for p in (prog, command) if p]
    out = Text()
    if prefix_parts:
        out.append(" ".join(prefix_parts) + ": ", style="bold")
    out.append(message, style=error_style)
    return out


def _body_row(label: str, value: str | Text) -> Text:
    """Render `  label:    value` — two-space indent, dim label, padded.

    The label column aligns to `_BODY_LABEL_WIDTH` so `field:`,
    `given:`, `source:`, and `expected:` sit in the same column.
    """
    out = Text("  ")
    key = f"{label}:"
    out.append(key, style="dim")
    # `max(1, ...)` keeps at least one space after labels longer than
    # the column (`sources tried:`) — without it they'd butt against
    # the value with no separator at all.
    out.append(" " * max(1, _BODY_LABEL_WIDTH - len(key)))
    if isinstance(value, Text):
        out.append_text(value)
    else:
        out.append(value)
    return out


def _help_footer(
    prog: str,
    command: str | None,
    *,
    suffix: str = "full options",
) -> Text:
    """Render `Run `prog [command] --help` for <suffix>.` in dim style."""
    target = prog if command is None else f"{prog} {command}"
    return Text(f"Run `{target} --help` for {suffix}.", style="dim")


def _join_lines(lines: Sequence[Text | str | None]) -> Text:
    """Join a sequence of lines into a single multi-line `Text`.

    `None` entries are dropped (used for conditional sections); plain
    strings become unstyled `Text` fragments. The empty string emits a
    blank line — the canonical separator between blocks.
    """
    out = Text()
    real: list[Text] = []
    for line in lines:
        if line is None:
            continue
        real.append(line if isinstance(line, Text) else Text(line))
    for i, line in enumerate(real):
        if i:
            out.append("\n")
        out.append_text(line)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Value-error rendering — single template across CLI/env/yaml
# ─────────────────────────────────────────────────────────────────────────────


def format_value_error(
    record: SourceValueRecord,
    *,
    detail: str = "",
    prog: str | None = None,
    command: str | None = None,
) -> Text:
    """Render a single multi-line template covering CLI/env/yaml.

    All four entry points (CLI parse error, env coerce error, YAML
    coerce error, validator failure) produce the same output shape so
    users learn the format once and recognize it everywhere. All
    rendering data is pre-computed in `record` — the renderer reads
    frozen fields and assembles styled lines.
    """
    from confline.config.types import SECRET_PLACEHOLDER  # noqa: PLC0415 — avoid cycle

    given_repr = SECRET_PLACEHOLDER if record.secret else repr(record.value)
    expected = detail or record.type_desc
    given_via = record.source_native_key or record.path

    lines: list[Text | str | None] = [
        _header_line(prog, command, f"invalid value for {given_via}"),
        "",
        _body_row("field", record.path),
        _body_row("given", given_repr),
        _body_row("source", record.source_label or "?"),
        _body_row("expected", expected),
    ]

    if record.suggestions:
        lines.append("")
        lines.append(_section_header("Try one of:"))
        lines.extend(_item_line(s) for s in record.suggestions)

    if prog is not None:
        lines.append("")
        lines.append(_help_footer(prog, command))

    return _join_lines(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Missing-required rendering
# ─────────────────────────────────────────────────────────────────────────────


def format_missing_required(
    error: MissingRequiredError,
    *,
    prog: str | None = None,
    command: str | None = None,
    label_sources: Sequence[Source] = (),  # noqa: ARG001 — kept for API parity
) -> Text:
    """Render `MissingRequiredError` per the `format_*_error` template.

    Header lists every missing field; per-field body names the expected
    type and the source chain that was attempted, then a `Try one of`
    block renders the pre-computed suggestions from each
    `MissingFieldRecord`.
    """
    fields = error.fields
    names = [f.path for f in fields]
    pluralize = "field" if len(fields) == 1 else "fields"
    sources_tried = ", ".join(error.sources_tried) if error.sources_tried else ""

    lines: list[Text | str | None] = [
        _header_line(
            prog, command, f"missing required {pluralize}: {_oxford_join(names)}",
        ),
    ]

    for field in fields:
        lines.append("")
        lines.append(_body_row("field", field.path))
        lines.append(_body_row("expected", field.type_desc))
        if sources_tried:
            lines.append(_body_row("sources tried", sources_tried))
        if field.suggestions:
            lines.append("")
            lines.append(_section_header("Try one of:"))
            lines.extend(_item_line(s) for s in field.suggestions)

    if prog is not None:
        lines.append("")
        lines.append(_help_footer(prog, command))

    return _join_lines(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Mutex-violation rendering
# ─────────────────────────────────────────────────────────────────────────────


_MUTEX_VERB_BOTH = 2  # wording threshold: `both` for two providers, `all` for 3+


def format_mutex_error(
    error: MutexViolationError,
    *,
    prog: str | None = None,
    command: str | None = None,
    label_sources: Sequence[Source] = (),
) -> Text:
    """Render a `MutexViolationError` for the operator.

    Two shapes:

    1. *Too many providers* (any group): names each provided field with
       its current value and originating source so the operator sees
       both sides at once. Lines render in source-native form
       (`--port 8080`, `MYAPP_PORT=8080`, `port: 8080`) using the
       pre-resolved data on each `ProvidedField`. Per-source key/value
       shapes come from `Source.display_kv_separator`; the
       channel-specific imperative comes from `Source.describe_unset_hint`.

    2. *Required group with no providers*: names the group and lists
       the available options. No values to print yet.

    `label_sources` is the active source chain — used to look up the
    source instance by name so the renderer can compose the line in
    source-native form via `display_kv_separator` and call
    `describe_unset_hint`. When the instance is missing, the renderer
    falls back to a generic `{key} = {value}` form.
    """
    if error.required and len(error.provided) == 0:
        opts = ", ".join(error.field_paths)
        return _join_lines([
            _header_line(prog, command, f"exactly one of [{opts}] must be set"),
            "",
            "These options form a required mutex group; pick one.",
        ])

    provided_paths = [p.path for p in error.provided]
    header = _oxford_join(provided_paths or error.field_paths)
    verb = (
        "cannot both be set"
        if len(provided_paths) == _MUTEX_VERB_BOTH
        else "cannot all be set"
    )

    lines: list[Text | str | None] = [
        _header_line(prog, command, f"{header} {verb}"),
        "",
    ]
    for entry in error.provided:
        lines.append(_mutex_provider_line(entry, label_sources))
    lines.append("")
    # Per-line hints already say *how* to unset each side; the footer
    # only needs to name the overall constraint.
    lines.append("These options are mutually exclusive — pick one.")
    return _join_lines(lines)


def _mutex_provider_line(
    entry: ProvidedField,
    label_sources: Sequence[Source] = (),
) -> Text:
    """Render one `  --port 8080  (from command line)` line.

    Reads value/key off the `ProvidedField` (value already redacted
    for secret fields, key already in source-native form). Body comes
    from the source's `display_kv_separator`; the action hint from
    `Source.describe_unset_hint`. With no source instance available
    the renderer falls back to a generic `{key} = {value}` body
    without a hint.
    """
    label = entry.source_native_key or entry.path
    value_str = _mutex_value_repr(entry)
    source = next(
        (s for s in label_sources if s.name == entry.source_name),
        None,
    )

    out = Text("  ")
    out.append(label, style=_source_key_style(entry.source_name))
    out.append(source.display_kv_separator if source is not None else " = ")
    out.append(value_str)
    out.append("    ")
    out.append(f"(from {_mutex_origin(entry, source)})", style="dim")

    hint = _mutex_unset_hint(entry, source, label)
    if hint:
        out.append(hint, style="dim")
    return out


def _mutex_value_repr(entry: ProvidedField) -> str:
    """Decide the display form for a mutex provider's value.

    `None` is replaced by `<set>` since the loader couldn't capture
    the raw value. Secret values are pre-redacted into
    `SECRET_PLACEHOLDER` upstream — render them bare (no repr quotes)
    so the placeholder reads as a placeholder, not a string literal.
    """
    if entry.value is None:
        return "<set>"
    if entry.secret:
        return str(entry.value)
    return repr(entry.value)


def _mutex_origin(
    entry: ProvidedField,
    source: Source | None,
) -> str:
    """Pick the human-facing origin label, falling back through three layers."""
    if entry.source_label:
        return entry.source_label
    if source is not None:
        return source.display_label
    return entry.source_name


def _mutex_unset_hint(
    entry: ProvidedField,
    source: Source | None,
    label: str,
) -> str:
    """Channel-specific imperative — empty when we can't name the action.

    Suppressed when the source can't name the field (`source_native_key`
    absent) or can't be found in `label_sources` (renderer called
    without sources). A generic placeholder would mislead.
    """
    if not entry.source_native_key or source is None:
        return ""
    return source.describe_unset_hint(label) or ""


# ─────────────────────────────────────────────────────────────────────────────
# Command-error rendering
# ─────────────────────────────────────────────────────────────────────────────


def format_unknown_command(
    error: UnknownCommandError,
    *,
    prog: str | None = None,
) -> Text:
    """Render an unknown subcommand with suggestions and known commands."""
    lines: list[Text | str | None] = [
        _header_line(prog, None, f"unknown command: {error.given!r}"),
    ]

    if error.suggestions:
        lines.append("")
        lines.append(_section_header("Did you mean:"))
        lines.extend(_item_line(f"  {s}") for s in error.suggestions)

    if error.available:
        lines.append("")
        lines.append(_section_header("Available commands:"))
        lines.extend(_item_line(f"  {name}") for name in error.available)

    if prog is not None:
        lines.append("")
        lines.append(_help_footer(prog, None, suffix="available commands"))

    return _join_lines(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Header helpers
# ─────────────────────────────────────────────────────────────────────────────


def _oxford_join(items: Sequence[str]) -> str:
    """English join with the oxford comma — `"a, b, and c"`.

    Two-item lists drop the comma (`"a and b"`); zero/one-item lists
    return the empty string / sole item. Used by mutex / missing-required
    headers so a 3+ field group reads naturally instead of stringing
    `" and "` between every item.
    """
    items = list(items)
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == _MUTEX_VERB_BOTH:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"
