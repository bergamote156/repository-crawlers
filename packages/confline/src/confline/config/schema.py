"""
Declarative schema types and the opt() field declaration.

`ConfigFieldInfo` / `ConfigGroup` / `ConfigSchema` are the schema shape
consumed by Sources and the parser builder. `opt()` is the user-facing field
declaration that attaches confline metadata to a dataclass field.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from collections.abc import Callable, Collection, Iterator
from dataclasses import MISSING, dataclass
from dataclasses import field as dc_field
from typing import TYPE_CHECKING, Any

from confline.config.types import MISSING_DEFAULT, FieldPath

if TYPE_CHECKING:
    # cycle: sources.base imports ConfigFieldInfo at runtime, so Source
    # can only be referenced here as a string annotation on excluded_from
    from confline.sources.base import Source

_OPT_SENTINEL: str = "__confline_opt__"


# ─────────────────────────────────────────────────────────────────────────────
# Schema dataclasses
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ConfigFieldInfo:
    """Per-field metadata produced by schema-build and consumed by Sources."""

    name: str
    path: FieldPath
    field_type: type
    is_optional: bool
    default: Any
    default_factory: Callable[[], Any] | None
    description: str
    choices: Collection[Any] | None
    validator: Callable[[Any], Any] | None
    excluded_from: "frozenset[type[Source]]"
    secret: bool
    deprecated: bool | str
    is_count: bool
    metavar: str | None
    show_default: bool
    annotated: tuple[Any, ...]
    nested_schema: "ConfigSchema | None"

    @property
    def has_default(self) -> bool:
        """True when the field has a non-MISSING default or a default_factory.

        Sentinel comparison is against `MISSING_DEFAULT` (alias of
        `dataclasses.MISSING`) — the same identity confline exposes
        publicly so users introspecting `ConfigFieldInfo.default`
        don't reach into `dataclasses` to compare.
        """
        return self.default is not MISSING_DEFAULT or self.default_factory is not None


@dataclass(frozen=True)
class ConfigGroup:
    """One group of fields contributed by a single config class in the MRO.

    Multiple groups appear when the schema is built from a class that
    inherits from several confline base classes — each contributes its
    own group, used for `--help` formatting later.
    """

    name: str
    description: str | None
    fields: tuple[ConfigFieldInfo, ...]
    is_mutex: bool = False
    mutex_required: bool = False


@dataclass(frozen=True)
class ConfigSchema:
    """Complete schema for a config class."""

    config_class: type
    groups: tuple[ConfigGroup, ...]
    model_validators: tuple[str, ...] = ()
    field_validators: dict[str, tuple[str, ...]] = dc_field(default_factory=dict)

    def all_fields(self) -> Iterator[ConfigFieldInfo]:
        for group in self.groups:
            yield from group.fields

    def find_field(self, name: str) -> ConfigFieldInfo | None:
        for f in self.all_fields():
            if f.name == name:
                return f
        return None


# ─────────────────────────────────────────────────────────────────────────────
# opt() — field declaration
# ─────────────────────────────────────────────────────────────────────────────


def opt(  # noqa: PLR0913
    default: Any = MISSING,
    *,
    default_factory: Callable[[], Any] | None = None,
    choices: Collection[Any] | None = None,
    validator: Callable[[Any], Any] | None = None,
    description: str = "",
    secret: bool = False,
    excluded_from: "Collection[type[Source]]" = (),
    deprecated: bool | str = False,
    count: bool = False,
    metavar: str | None = None,
    show_default: bool = False,
) -> Any:
    """Declare a confline-managed dataclass field.

    All confline-known knobs go through here. Source-specific naming
    (CLI flag, ENV var name, YAML path) lives in `Annotated[...]`
    instead — see `confline.sources`.

    `excluded_from` lists `Source` subclasses that should skip the
    field at resolution time, e.g. `excluded_from=[CliSource]`.
    """
    if default is not MISSING and default_factory is not None:
        raise ValueError("opt(): cannot set both default and default_factory")

    metadata = {
        _OPT_SENTINEL: True,
        "description": description,
        "choices": choices,
        "validator": validator,
        "secret": secret,
        "excluded_from": frozenset(excluded_from),
        "deprecated": deprecated,
        "count": count,
        "metavar": metavar,
        "show_default": show_default,
    }

    if default_factory is not None:
        return dc_field(default_factory=default_factory, metadata=metadata)
    if default is MISSING:
        return dc_field(metadata=metadata)
    if _is_known_mutable(default):
        # `dataclasses.field` rejects mutable defaults; convert to a
        # factory that hands each instance its own copy. Captures the
        # value at opt() call time, matching Python default-arg semantics.
        captured = default
        return dc_field(
            default_factory=lambda: type(captured)(captured),
            metadata=metadata,
        )
    return dc_field(default=default, metadata=metadata)


def _is_known_mutable(value: Any) -> bool:
    return isinstance(value, (list, dict, set))
