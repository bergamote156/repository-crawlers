"""
Help-text rendering — `help=` strings and the `ConflineHelpFormatter`.

Two layers cooperate to produce per-option help:

- `help_text(field)` — the one-line `help=` string handed to argparse;
  argparse wraps it as the option's body column.
- `ConflineHelpFormatter` — a `rich-argparse` subclass that appends a
  metadata block under each option header. The block is one inline
  line of `default: <value> · env: <key> · yaml: <path>` (plus any
  custom sources), followed when relevant by a tag line such as
  `[secret] · [deprecated] · [mutex: <group>]`.

Theming/colour flows through `rich-argparse`; `NO_COLOR` and a non-tty
stderr fall back to plain text without extra wiring on our side.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import argparse
from collections.abc import Iterator, Sequence
from dataclasses import MISSING
from typing import Any, ClassVar

from rich.text import Text
from rich_argparse import RawDescriptionRichHelpFormatter

from confline.config.schema import ConfigFieldInfo
from confline.config.types import SECRET_PLACEHOLDER
from confline.sources.base import Source

# ─────────────────────────────────────────────────────────────────────────────
# Public API — `help=` string
# ─────────────────────────────────────────────────────────────────────────────


def help_text(field: ConfigFieldInfo) -> str:
    """Build the one-line `help=` string for an argparse action.

    Description-only by design — defaults, source labels, and tags are
    rendered separately by `ConflineHelpFormatter` so each gets its
    own line and its own style.
    """
    parts: list[str] = []
    if field.description:
        parts.append(field.description)
    if field.is_count:
        parts.append("(stackable: -v, -vv, -vvv)")
    return " ".join(parts) if parts else ""


# ─────────────────────────────────────────────────────────────────────────────
# Theme — confline styles layered onto rich-argparse defaults
# ─────────────────────────────────────────────────────────────────────────────


# Plain foreground colours, no italics or backgrounds — terminals
# render `italic`/`bold italic` inconsistently and the previous
# theme produced a "highlighted block" look that competed with the
# option header for attention.
_STYLES: dict[str, Any] = {
    **RawDescriptionRichHelpFormatter.styles,
    "confline.label": "dim",  # "default:", "env:", "yaml:" prefixes
    "confline.value": "default",  # default value rendering
    "confline.envvar": "yellow",  # MYAPP_PORT
    "confline.yamlpath": "magenta",  # db.host
    "confline.separator": "dim",  # " · " between metadata segments
    "confline.required": "bold red",  # `<required>` in the default segment
    "confline.tag": "italic dim",  # [deprecated], [mutex: ...]
    "confline.secret": "bold red",  # [secret]
}

_SEGMENT_SEPARATOR = " · "


# ─────────────────────────────────────────────────────────────────────────────
# Formatter class — thin shell that delegates rendering
# ─────────────────────────────────────────────────────────────────────────────


class ConflineHelpFormatter(RawDescriptionRichHelpFormatter):
    """rich-argparse formatter that appends a per-field metadata block.

    Subclasses set `label_sources` (a class attribute) to inject the
    source list to label against; `build_argparse_parser` builds a
    closure subclass with that attribute set. Stock `rich-argparse`
    pads our `(empty_header, line)` yields to the help column so the
    metadata aligns under the description without re-implementing
    `_Section._render_actions`.
    """

    # Subclasses (built by `build_argparse_parser`) override this.
    label_sources: ClassVar[Sequence[Source]] = ()

    # Keep argparse's stock heading capitalisation — group titles like
    # `db (HostConfig)` stay verbatim instead of being title-cased to
    # `Db (Hostconfig)`.
    group_name_formatter: ClassVar[Any] = staticmethod(lambda s: s)

    styles: ClassVar[dict[str, Any]] = _STYLES

    def _rich_format_action(
        self,
        action: argparse.Action,
    ) -> Iterator[tuple[Text, Text | None]]:
        # Standard rendering first — header + the main help line.
        yield from super()._rich_format_action(action)
        field: ConfigFieldInfo | None = getattr(action, "_confline_field", None)
        if field is None or action.help is argparse.SUPPRESS:
            return
        for line in _render_extras_lines(action, field, self.label_sources):
            yield Text(""), line


# ─────────────────────────────────────────────────────────────────────────────
# Per-action extras — inline metadata line + optional tag line
# ─────────────────────────────────────────────────────────────────────────────


def _render_extras_lines(
    action: argparse.Action,
    field: ConfigFieldInfo,
    label_sources: Sequence[Source],
) -> list[Text]:
    """Build the lines yielded under one action — 0, 1, or 2."""
    out: list[Text] = []
    metadata = _render_metadata_line(field, label_sources)
    if metadata is not None:
        out.append(metadata)
    tags = _render_tag_line(action, field)
    if tags is not None:
        out.append(tags)
    return out


def _render_metadata_line(
    field: ConfigFieldInfo,
    label_sources: Sequence[Source],
) -> Text | None:
    """Inline `default: 8080 · env: MYAPP_PORT · yaml: port` line.

    The `default:` segment is always present (covers the `<required>`
    case too). Source segments appear in `label_sources` order, so the
    operator sees the resolution chain left-to-right.
    """
    segments: list[Text] = [_default_segment(field)]
    for source in label_sources:
        seg = _source_segment(source, field)
        if seg is not None:
            segments.append(seg)
    return _join_segments(segments)


def _render_tag_line(
    action: argparse.Action,
    field: ConfigFieldInfo,
) -> Text | None:
    """Inline `[secret] · [deprecated] · [mutex: Mode]` line, or None."""
    tags: list[Text] = []

    if field.secret:
        tags.append(Text("[secret]", style="confline.secret"))

    if field.deprecated:
        label = "[deprecated]" if field.deprecated is True else f"[deprecated: {field.deprecated}]"
        tags.append(Text(label, style="confline.tag"))

    mutex_group = getattr(action, "_confline_mutex_group", None)
    if mutex_group:
        tags.append(Text(f"[mutex: {mutex_group}]", style="confline.tag"))
        sibling_fields = getattr(action, "_confline_mutex_group_fields", ())
        if _is_unique_default_in_mutex(field, sibling_fields):
            tags.append(Text("[active by default]", style="confline.tag"))

    return _join_segments(tags) if tags else None


# ─────────────────────────────────────────────────────────────────────────────
# Segment builders — `<label>: <value>` fragments + joining
# ─────────────────────────────────────────────────────────────────────────────


def _default_segment(field: ConfigFieldInfo) -> Text:
    """Render the `default: …` segment for one field.

    Three shapes:
    - `default_factory` — `factory_name()` (factory never invoked)
    - `default is MISSING` — `<required>` in the alert style
    - otherwise — `repr(default)`, redacted to the secret placeholder
      when the field is marked secret
    """
    if field.default_factory is not None:
        name = getattr(field.default_factory, "__name__", "factory")
        return _kv_segment("default", f"{name}()", value_style="confline.value")
    if field.default is MISSING:
        return _kv_segment("default", "<required>", value_style="confline.required")
    rendered = SECRET_PLACEHOLDER if field.secret else repr(field.default)
    return _kv_segment("default", rendered, value_style="confline.value")


def _source_segment(
    source: Source,
    field: ConfigFieldInfo,
) -> Text | None:
    """Render one `env: MYAPP_PORT` segment, or `None` when the source
    has nothing to say about this field.

    Three skip conditions:
    - source opts out via `display_in_help_block=False` (e.g. CliSource,
      whose label already shows in the action header)
    - the source doesn't support this field type (`supports_field`)
    - the source returns `None` from `describe_field` (no key to show)
    """
    if not source.display_in_help_block:
        return None
    if not type(source).supports_field(field):
        return None
    key = source.describe_field(field)
    if key is None:
        return None
    # `display_label` (operator-facing) over `name` (wire id) — plugin
    # authors get readable labels for free.
    style = _SOURCE_VALUE_STYLES.get(source.name, "confline.value")
    return _kv_segment(source.display_label, key, value_style=style)


_SOURCE_VALUE_STYLES = {
    "env": "confline.envvar",
    "yaml": "confline.yamlpath",
}


def _kv_segment(label: str, value: str, *, value_style: str) -> Text:
    """Build one `label: value` fragment with per-part styling."""
    seg = Text()
    seg.append(f"{label}:", style="confline.label")
    seg.append(" ")
    seg.append(value, style=value_style)
    return seg


def _join_segments(segments: Sequence[Text]) -> Text:
    """Join Text fragments with the dim middle-dot separator."""
    out = Text()
    for i, seg in enumerate(segments):
        if i:
            out.append(_SEGMENT_SEPARATOR, style="confline.separator")
        out.append_text(seg)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Mutex helpers — `[active by default]` visibility rules
# ─────────────────────────────────────────────────────────────────────────────


def _has_static_default(field: ConfigFieldInfo) -> bool:
    """True when the field carries a non-MISSING, non-None scalar default.

    `default_factory` is skipped so help rendering stays side-effect-free.
    """
    return field.default is not MISSING and field.default is not None


def _is_unique_default_in_mutex(
    field: ConfigFieldInfo,
    group_fields: Sequence[ConfigFieldInfo],
) -> bool:
    """True when *only* this field in the mutex group has a static default.

    With multiple defaults, the "active by default" choice is no longer
    deterministic (mutex enforcement counts both as defaults, so the
    user-provided count stays 0 — but the operator can't tell which
    side actually runs). Suppressing the tag in that case avoids a
    false signal; the bare `[mutex: …]` tag still says they conflict.
    """
    defaults = [f for f in group_fields if _has_static_default(f)]
    # `name` over `is`: argparse_builder stamps a `dataclasses.replace`d
    # field with the full dotted path, so identity comparison against
    # the original `group.fields` tuple would always miss.
    return len(defaults) == 1 and defaults[0].name == field.name
