"""
Environment-variable source.

Markers exported here:
- `EnvAlias("LEGACY_NAME")` — override the auto-derived var name

To exclude a field from env resolution, pass `EnvSource` itself to
`opt(excluded_from=[EnvSource])`.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

from confline.config.base import is_list_of_config_base
from confline.config.schema import ConfigFieldInfo, ConfigSchema
from confline.config.types import FieldPath
from confline.errors import EnvKeyCollisionError
from confline.sources.base import NO_VALUE, Source


@dataclass(frozen=True)
class EnvAlias:
    """Override the environment-variable name for a field.

    Usage: `Annotated[str, EnvAlias("LEGACY_KEY")]`.
    """

    name: str


class EnvSource(Source):
    """Resolve fields from a process-environment-shaped mapping.

    Empty strings (`PORT=`) are treated as `NO_VALUE` — colloquially
    "not set" in shell contexts. Apps needing literal-empty semantics
    override at a higher layer.
    """

    name: ClassVar[str] = "env"
    display_label: ClassVar[str] = "environment"
    display_kv_separator: ClassVar[str] = "="

    def __init__(
        self,
        env: Mapping[str, str],
        *,
        prefix: str = "",
        delimiter: str = "__",
    ) -> None:
        self._env = env
        self._prefix = prefix
        self._delimiter = delimiter

    def validate_schema(self, schema: ConfigSchema) -> None:
        _validate_schema_for_env_source(
            schema,
            prefix=self._prefix,
            delimiter=self._delimiter,
        )

    @classmethod
    def supports_field(cls, field: ConfigFieldInfo) -> bool:
        # Env vars are flat string key/value — `list[ConfigBase]`
        # (list of dicts) has no canonical encoding here. YAML carries
        # this natively.
        return not is_list_of_config_base(field.field_type)

    def resolve(self, field: ConfigFieldInfo) -> Any:
        key = self._key_for(field)
        if key not in self._env:
            return NO_VALUE

        raw = self._env[key]
        if raw == "":
            return NO_VALUE

        return raw

    def _describe_field(self, field: ConfigFieldInfo) -> str | None:
        return self._key_for(field)

    def describe_unset_hint(self, key: str) -> str | None:
        return f" — unset {key}"

    def _key_for(self, field: ConfigFieldInfo) -> str:
        return _derive_key(field, prefix=self._prefix, delimiter=self._delimiter)


def _validate_schema_for_env_source(
    schema: ConfigSchema,
    *,
    prefix: str = "",
    delimiter: str = "__",
) -> None:
    """Schema-only env-key collision check.

    Raises `EnvKeyCollisionError` if two fields would derive the same
    env-var name under the given `(prefix, delimiter)`. Most useful in
    app integration tests that import the schema and want to fail at CI
    time rather than at first runtime.

    Optimisation: the default `delimiter="__"` together with no
    underscores in any field name or path component makes a collision
    mathematically impossible, so the walk is skipped. Custom delimiters
    or `_` in names always run the full check.
    """
    if delimiter == "__" and not _any_underscore_in_paths(schema):
        return

    seen: dict[str, str] = {}

    def walk(s: ConfigSchema, p: FieldPath) -> None:
        for f in s.all_fields():
            full = p + f.path
            if EnvSource in f.excluded_from:
                continue

            if f.nested_schema is not None:
                walk(f.nested_schema, full)
                continue

            view = dataclasses.replace(f, path=full)
            key = _derive_key(view, prefix=prefix, delimiter=delimiter)
            dotted = ".".join(full)
            if key in seen and seen[key] != dotted:
                raise EnvKeyCollisionError(
                    key=key,
                    field_a=seen[key],
                    field_b=dotted,
                )
            seen[key] = dotted

    walk(schema, ())


def _any_underscore_in_paths(schema: ConfigSchema) -> bool:
    """True if any field name (top-level or nested) contains `_`.

    Used by `EnvSource.validate_schema` to skip the walk when the
    default delimiter `__` cannot collide — `foo_bar` (top) and
    `foo.bar` (nested) only collapse when a name contains `_`.
    """
    for field in schema.all_fields():
        for component in field.path:
            if "_" in component:
                return True

        if field.nested_schema is not None and _any_underscore_in_paths(
            field.nested_schema,
        ):
            return True

    return False


def _derive_key(field: ConfigFieldInfo, *, prefix: str, delimiter: str) -> str:
    """Pure derivation — no instance state. Honours `EnvAlias`."""
    alias: EnvAlias | None = None
    for m in field.annotated:
        if isinstance(m, EnvAlias):
            alias = m

    if alias is not None:
        return alias.name

    return prefix + delimiter.join(p.upper() for p in field.path)
