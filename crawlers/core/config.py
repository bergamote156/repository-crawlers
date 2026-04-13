"""
Configuration Management.

Base configuration classes and helpers for the crawler framework.
Uses dataclasses for configuration definition.
"""

# pylint: disable=too-few-public-methods

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import MISSING, Field, dataclass, field, is_dataclass
from types import NoneType, UnionType
from typing import Any, ClassVar, Iterator, Union, get_args, get_origin, get_type_hints

# ─────────────────────────────────────────────────────────────────────────────
# Schema Data Structures
# ─────────────────────────────────────────────────────────────────────────────


class ConfigBase:
    """
    Base class for configuration classes.

    All config classes should inherit from this (directly or indirectly).
    Automatically applies @dataclass and builds __config_schema__ via __init_subclass__.

    Usage:
        class MyConfig(ConfigBase):
            field: str = opt("default", description="My field")

        # For non-keyword-only fields:
        class MyConfig(ConfigBase, kw_only=False):
            ...
    """

    __config_schema__: ClassVar["ConfigSchema"]

    def __init_subclass__(cls, *, kw_only: bool = True, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

        # Skip if already processed (handles multiple inheritance)
        if hasattr(cls, "__config_schema__"):
            existing = cls.__config_schema__
            if existing.config_class is cls:
                return

        # Apply @dataclass
        dataclass(kw_only=kw_only)(cls)
        cls.__config_schema__ = _build_schema(cls)


def opt(
    default: Any = ...,
    *,
    cli: str | tuple[str, ...] | bool | None = None,
    env: str | bool | None = None,
    yaml_key: str | bool | None = None,
    description: str = "",
    **kwargs,
) -> Any:
    """
    Dataclass field wrapper with CLI/ENV/YAML metadata.

    Args:
        default: Default value. Use ... (Ellipsis) for required fields.
        cli: CLI argument name(s).
             - None (default): Auto-generate flag name (e.g. "my_field" -> "--my-field")
             - str: Explicit name (e.g. "-f" or "--foo")
             - tuple: Multiple aliases (e.g. ("--foo", "-f"))
             - False: Disable CLI argument generation
        env: Environment variable suffix.
             - None (default): Auto-generate from field name (upper case)
             - str: Explicit suffix (e.g. "MY_VAR")
             - False: Disable environment variable
        yaml_key: Key in YAML config.
             - None (default): Use field name
             - str: Explicit key
             - False: Disable YAML loading
        description: Help text for CLI and documentation.
        **kwargs: Additional dataclasses.field arguments (e.g. default_factory).
    """
    metadata: dict[str, Any] = {
        "is_config_field": True,
        "description": description,
    }

    if cli is False:
        metadata["cli_disabled"] = True
    elif cli is not None:
        metadata["cli"] = (cli,) if isinstance(cli, str) else cli

    if env is False:
        metadata["env_disabled"] = True
    elif env is not None:
        metadata["env"] = env

    if yaml_key is False:
        metadata["yaml_disabled"] = True
    elif yaml_key is not None:
        metadata["yaml_key"] = yaml_key

    # Handle default vs default_factory vs required
    field_kwargs = kwargs.copy()
    if default is not ...:
        field_kwargs["default"] = default

    # pylint: disable=invalid-field-call
    return field(metadata=metadata, **field_kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# Schema Building Helpers
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class CliInfo:
    """Pre-computed CLI info for argparse."""

    names: tuple[str, ...]  # e.g. ("-n", "--max-records")
    kwargs: dict[str, Any]  # e.g. type=int, help="...", action="store_true"
    is_positional: bool
    attr_name: str  # Attribute name in argparse Namespace (e.g. "max_records")


@dataclass
class ConfigFieldInfo:
    """Complete info about a config field."""

    # pylint: disable=too-many-instance-attributes

    name: str
    field_type: type  # Actual type after unwrapping Optional
    description: str
    default: Any
    required: bool

    cli: CliInfo | None  # None = CLI disabled
    env_var: str | None  # Full env var name e.g. "CRAWLER_BASE_URL"
    yaml_key: str | None  # YAML key or None if disabled

    nested_schema: "ConfigSchema | None" = None


@dataclass
class ConfigGroup:
    """A group of config fields from one class in the hierarchy."""

    name: str  # Class.__name__
    description: str | None  # Class.__doc__
    fields: list[ConfigFieldInfo]


@dataclass
class ConfigSchema:
    """Complete schema for a config class - built once by @config decorator."""

    config_class: type[ConfigBase]
    groups: list[ConfigGroup]  # Most specific class first

    def all_fields(self) -> Iterator[ConfigFieldInfo]:
        """Iterate all fields across all groups (flat)."""
        for group in self.groups:
            yield from group.fields


def _build_schema(config_cls: type) -> ConfigSchema:
    """Build complete ConfigSchema from a dataclass config class."""
    groups: list[ConfigGroup] = []
    seen_fields: set[str] = set()

    type_hints = get_type_hints(config_cls)

    # Walk MRO from most specific to most general
    for cls in config_cls.__mro__:
        if not is_dataclass(cls) or cls is object:
            continue

        # Get fields defined directly in this class
        own_field_names = _get_own_field_names(cls)

        group_fields: list[ConfigFieldInfo] = []

        for field_name in own_field_names:
            if field_name in seen_fields:
                continue  # Already processed in more specific class

            seen_fields.add(field_name)
            field_obj = cls.__dataclass_fields__[field_name]
            annotation = type_hints.get(field_name, field_obj.type)
            info = _build_field_info(field_obj, annotation)
            group_fields.append(info)

        if group_fields:
            groups.append(
                ConfigGroup(
                    name=cls.__name__,
                    description=cls.__doc__,
                    fields=group_fields,
                )
            )

    return ConfigSchema(config_class=config_cls, groups=groups)


def _get_own_field_names(cls: type) -> set[str]:
    """Get field names defined directly in cls, not inherited."""
    if not is_dataclass(cls):
        return set()

    own = set(cls.__dataclass_fields__.keys()) & set(cls.__annotations__.keys())

    return own


def _build_field_info(field_obj: Field, annotation: type) -> ConfigFieldInfo:
    """Build ConfigFieldInfo from a dataclass field."""
    metadata = dict(field_obj.metadata)
    field_name = field_obj.name

    actual_type, _ = _unwrap_optional(annotation)

    is_nested = is_dataclass(actual_type) and isinstance(actual_type, type)
    nested_schema = _build_schema(actual_type) if is_nested else None

    required = field_obj.default is MISSING and field_obj.default_factory is MISSING

    default: Any = None
    if field_obj.default is not MISSING:
        default = field_obj.default
    elif field_obj.default_factory is not MISSING:
        default = field_obj.default_factory  # keep factory reference, don't call it

    cli = None if is_nested else _build_cli_info(field_name, metadata, actual_type)

    env_var = None
    if not metadata.get("env_disabled"):
        env_suffix = metadata.get("env") or field_name.upper()
        env_var = f"CRAWLER_{env_suffix}"

    yaml_key = None
    if not metadata.get("yaml_disabled"):
        yaml_key = metadata.get("yaml_key") or field_name

    return ConfigFieldInfo(
        name=field_name,
        field_type=actual_type,
        description=metadata.get("description", ""),
        default=default,
        required=required,
        cli=cli,
        env_var=env_var,
        yaml_key=yaml_key,
        nested_schema=nested_schema,
    )


def _unwrap_optional(annotation: type) -> tuple[type, bool]:
    """Unwrap Optional[X] / Union[X, None] to (X, True), or (annotation, False)."""
    origin = get_origin(annotation)

    # Handle both typing.Union and types.UnionType (Python 3.10+ syntax: X | Y)
    if origin is Union or isinstance(annotation, UnionType):
        args = get_args(annotation)
        non_none = [a for a in args if a is not NoneType]
        if len(non_none) == 1:
            return non_none[0], True

    return annotation, False


def _build_cli_info(field_name: str, metadata: dict[str, Any], actual_type: type) -> CliInfo | None:
    """Build CliInfo from field metadata, or None if CLI disabled."""
    if metadata.get("cli_disabled"):
        return None

    cli_explicit = metadata.get("cli")
    if cli_explicit:
        names = (cli_explicit,) if isinstance(cli_explicit, str) else tuple(cli_explicit)
    else:
        # auto-generate: my_field -> --my-field
        names = (f"--{field_name.replace('_', '-')}",)

    is_positional = not str(names[0]).startswith("-")

    kwargs: dict[str, Any] = {}

    if metadata.get("description"):
        kwargs["help"] = metadata["description"]

    if actual_type is bool:
        kwargs["action"] = "store_true"
    elif actual_type in (int, float, str):
        kwargs["type"] = actual_type

    if is_positional:
        # argparse uses the positional name directly as dest
        attr_name = names[0]
    else:
        # dest ensures attr_name == field_name regardless of flag spelling
        kwargs["dest"] = field_name
        kwargs["default"] = None
        attr_name = field_name

    return CliInfo(names=names, kwargs=kwargs, is_positional=is_positional, attr_name=attr_name)
