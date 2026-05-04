"""
`ConfigBase`, `MutuallyExclusiveGroup`, schema build, and type predicates.

`ConfigBase.__init_subclass__` auto-decorates subclasses as kw-only
dataclasses and builds `__config_schema__` at class-creation time —
no decorator on user code, no runtime build cost.

`is_config_class` and `is_list_of_config_base` are the canonical
predicates for call sites that need to distinguish config types from
plain types (loader, command discovery, schema build).
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import inspect
from dataclasses import MISSING, Field, dataclass, is_dataclass
from dataclasses import fields as dc_fields
from types import NoneType, UnionType
from typing import (
    Any,
    ClassVar,
    Union,
    dataclass_transform,
    get_args,
    get_origin,
    get_type_hints,
)

from confline.config.schema import (
    _OPT_SENTINEL,
    ConfigFieldInfo,
    ConfigGroup,
    ConfigSchema,
)
from confline.config.types import SECRET_PLACEHOLDER, FieldPath, Provenance
from confline.config.validators import collect_field_validators, collect_model_validators

# ─────────────────────────────────────────────────────────────────────────────
# Schema build (must be defined before ConfigBase subclasses are created)
# ─────────────────────────────────────────────────────────────────────────────


def _build_schema(config_cls: type) -> ConfigSchema:
    """Walk the MRO bottom-up, collect fields with earliest-MRO-wins."""
    groups: list[ConfigGroup] = []
    seen: set[str] = set()
    type_hints = get_type_hints(config_cls, include_extras=True)

    for cls in config_cls.__mro__:
        if cls is object or not is_dataclass(cls):
            continue

        own_names = _own_field_names(cls)
        new_fields: list[ConfigFieldInfo] = []

        for name in own_names:
            if name in seen:
                continue
            seen.add(name)

            field_obj = cls.__dataclass_fields__[name]
            annotation = type_hints.get(name, field_obj.type)
            new_fields.append(_build_field_info(field_obj, annotation))

        if not new_fields:
            continue

        # Detect mutex groups via attribute marker, not MRO `__name__`
        # walk: a renamed `MutuallyExclusiveGroup` would silently turn
        # off enforcement under the string check. The marker is set in
        # `MutuallyExclusiveGroup.__init_subclass__` and skipped on the
        # marker class itself.
        is_mutex = bool(getattr(cls, "__confline_mutex__", False))
        mutex_required = bool(getattr(cls, "__mutex_required__", False)) if is_mutex else False

        groups.append(
            ConfigGroup(
                name=cls.__name__,
                description=_first_paragraph(cls.__doc__),
                fields=tuple(new_fields),
                is_mutex=is_mutex,
                mutex_required=mutex_required,
            )
        )

    return ConfigSchema(
        config_class=config_cls,
        groups=tuple(groups),
        model_validators=collect_model_validators(config_cls),
        field_validators=collect_field_validators(config_cls),
    )


def _first_paragraph(doc: str | None) -> str | None:
    """First paragraph of `doc` — text up to the first blank line.

    PEP 257 docstrings put a one-sentence summary first, then a blank
    line, then details. The summary is what `--help` shows under each
    argument group; the rest is reference material for developers and
    would only crowd the help output. Returns `None` for missing or
    blank docstrings.
    """
    if not doc:
        return None
    cleaned = inspect.cleandoc(doc)
    if not cleaned:
        return None
    paragraph = cleaned.split("\n\n", 1)[0].strip()
    return paragraph or None


def _own_field_names(cls: type) -> list[str]:
    """Field names declared directly on `cls` (not inherited).

    Uses `dataclasses.fields()` rather than `__dataclass_fields__` so
    ClassVar attributes (which leak into `__dataclass_fields__` as an
    implementation detail) stay out of the schema.
    """
    if not is_dataclass(cls):
        return []

    own_annotated = set(getattr(cls, "__annotations__", {}).keys())
    return [f.name for f in dc_fields(cls) if f.name in own_annotated]


def _build_field_info(field_obj: Field, annotation: Any) -> ConfigFieldInfo:
    inner, annotated_meta = _split_annotated(annotation)
    actual_type, is_optional = _unwrap_optional(inner)

    opt_meta = field_obj.metadata if field_obj.metadata.get(_OPT_SENTINEL) else {}

    excluded_from = set(opt_meta.get("excluded_from", frozenset()))

    if field_obj.default is not MISSING:
        default: Any = field_obj.default
        default_factory = None
    elif field_obj.default_factory is not MISSING:
        default = MISSING
        default_factory = field_obj.default_factory
    else:
        default = MISSING
        default_factory = None

    nested_schema = None
    if is_config_class(actual_type):
        nested_schema = actual_type.__config_schema__

    return ConfigFieldInfo(
        name=field_obj.name,
        path=(field_obj.name,),
        field_type=actual_type,
        is_optional=is_optional,
        default=default,
        default_factory=default_factory,
        description=opt_meta.get("description", ""),
        choices=opt_meta.get("choices"),
        validator=opt_meta.get("validator"),
        excluded_from=frozenset(excluded_from),
        secret=bool(opt_meta.get("secret", False)),
        deprecated=opt_meta.get("deprecated", False),
        is_count=bool(opt_meta.get("count", False)),
        metavar=opt_meta.get("metavar"),
        show_default=bool(opt_meta.get("show_default", False)),
        annotated=tuple(annotated_meta),
        nested_schema=nested_schema,
    )


def _split_annotated(annotation: Any) -> tuple[Any, tuple[Any, ...]]:
    """Split `Annotated[T, m1, m2]` into `(T, (m1, m2))`.

    Returns `(annotation, ())` for non-Annotated inputs. Reads
    `__metadata__` / `__origin__` directly — these are the documented
    Annotated attributes and the only reliable check across CPython
    versions.
    """
    if hasattr(annotation, "__metadata__") and hasattr(annotation, "__origin__"):
        return annotation.__origin__, tuple(annotation.__metadata__)
    return annotation, ()


def _unwrap_optional(annotation: Any) -> tuple[Any, bool]:
    """Strip a single `None` from `T | None` / `Optional[T]`."""
    origin = get_origin(annotation)
    if origin is Union or isinstance(annotation, UnionType):
        args = get_args(annotation)
        non_none = [a for a in args if a is not NoneType]
        if len(non_none) == 1 and len(non_none) != len(args):
            return non_none[0], True
    return annotation, False


# ─────────────────────────────────────────────────────────────────────────────
# ConfigBase
# ─────────────────────────────────────────────────────────────────────────────


@dataclass_transform(kw_only_default=True)
class ConfigBase:
    """Base class for declarative config objects.

    Subclasses are auto-decorated with `@dataclass(kw_only=True)` and
    receive `__config_schema__` at class-creation time.
    """

    __config_schema__: ClassVar[ConfigSchema]

    def __repr__(self) -> str:
        # Default-on secret redaction: print(config), logger.info("loaded
        # %s", config), and extra={"cfg": config} all funnel through
        # __repr__, so this is the chokepoint. Defined on the base class
        # with `dataclass(repr=False)` in `__init_subclass__` so
        # dataclass doesn't overwrite it.
        schema = type(self).__config_schema__
        parts: list[str] = []
        for f in schema.all_fields():
            value = getattr(self, f.name, None)
            rendered = SECRET_PLACEHOLDER if f.secret else repr(value)
            parts.append(f"{f.name}={rendered}")
        return f"{type(self).__name__}({', '.join(parts)})"

    def _attach_provenance(self, provenance: dict[FieldPath, Provenance]) -> None:
        """Stamp this instance with per-field provenance.

        Called by the resolver once the instance is fully constructed.
        `object.__setattr__` rather than plain assignment so future
        frozen `ConfigBase` variants don't reject the attach.
        """
        object.__setattr__(self, "__confline_provenance__", provenance)

    def _get_provenance(self) -> dict[FieldPath, Provenance] | None:
        """Return the attached provenance map, or None.

        Hand-built instances and nested children of a resolved root both
        return None — only the resolved root carries the map.
        """
        return getattr(self, "__confline_provenance__", None)

    def source_of(self, path: str | FieldPath) -> Provenance:
        """Return where the field at `path` was resolved from.

        `path` is dotted (`"db.host"`) or a tuple (`("db", "host")`).
        Available only on instances built by `load_config`. Provenance
        is stored on the root instance — for nested fields, query the
        root with the full dotted path rather than walking into the
        nested config and asking it locally.

        Raises `KeyError` with an actionable hint when the path can't
        be resolved: distinguishes "this is a nested instance, ask the
        root" from "this instance was hand-built without load_config"
        from "this field was never produced by any source".
        """
        key: FieldPath = tuple(path.split(".")) if isinstance(path, str) else tuple(path)
        path_repr = ".".join(key)

        provenance = self._get_provenance()
        if provenance is None:
            # Two cases collapse here for the caller: (a) a *nested*
            # ConfigBase instance reached via attribute walk (the root
            # carries provenance, not the children) and (b) a config
            # built by hand without going through load_config. Junior
            # debuggers hit (a) constantly because method dispatch via
            # inheritance silently dispatches the call to the nested
            # instance — name both possibilities so they can pick.
            raise KeyError(
                f"provenance is tracked only on the root config built by "
                f"load_config — query the top-level instance with the full "
                f"dotted path (e.g. 'db.{path_repr}'), not the nested "
                f"instance",
            )

        if key not in provenance:
            raise KeyError(
                f"field {path_repr!r} was not provided by any source — "
                f"either the path is a typo or no source resolved a value "
                f"for that field",
            )

        return provenance[key]

    def __init_subclass__(cls, *, kw_only: bool = True, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

        # Avoid double-init when a subclass is already a fully-built schema.
        if "__config_schema__" in cls.__dict__:
            return

        # `is_dataclass` returns True for any class inheriting from a
        # dataclass — even if the subclass has not been decorated itself.
        # Check the class's own `__dict__` to detect that and re-decorate
        # so the subclass picks up its newly-declared fields.
        original_doc = cls.__doc__
        if "__dataclass_fields__" not in cls.__dict__:
            # `repr=False` so dataclass doesn't overwrite the redacting
            # `__repr__` defined on `ConfigBase`.
            dataclass(kw_only=kw_only, repr=False)(cls)
        # `dataclass()` overwrites `__doc__` with an auto-generated
        # signature dump that leaks every field's default value. Restore
        # the user-authored docstring (or `None`) so help renderers and
        # secret-field redaction stay honest.
        cls.__doc__ = original_doc
        cls.__config_schema__ = _build_schema(cls)


class MutuallyExclusiveGroup(ConfigBase):
    """Marker subclass — fields declared here participate in mutex."""

    __mutex_required__: ClassVar[bool] = False
    __confline_mutex__: ClassVar[bool] = False  # the marker class itself isn't a group

    def __init_subclass__(
        cls,
        *,
        kw_only: bool = True,
        required: bool = False,
        **kwargs: Any,
    ) -> None:
        cls.__mutex_required__ = required
        cls.__confline_mutex__ = True
        super().__init_subclass__(kw_only=kw_only, **kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# Type predicates
# ─────────────────────────────────────────────────────────────────────────────


def is_config_class(t: Any) -> bool:
    """Return True if `t` is a `ConfigBase` subclass.

    Single canonical test for "is this a confline config class?" —
    call sites in loader, command discovery, and schema build use
    this helper instead of inlining `isinstance/issubclass` or
    duck-typing on `__config_schema__`. Nominal beats duck so the
    error message can name the contract directly ("must subclass
    ConfigBase") and the answer is consistent across modules.
    """
    return isinstance(t, type) and issubclass(t, ConfigBase)


def is_list_of_config_base(annotation: Any) -> bool:
    """True for `list[X]` where X is a `ConfigBase` subclass.

    Sources call this from `supports_field` to declare they cannot
    handle list-of-nested-config shapes — argparse and env vars are
    flat key/value spaces, only YAML delivers list-of-dicts natively.
    """
    if get_origin(annotation) is not list:
        return False
    args = get_args(annotation)
    return len(args) == 1 and is_config_class(args[0])
