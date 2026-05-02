"""
YAML source — resolves fields from one or more pre-prepared dict scopes.

Markers exported here:
- `YamlPath("legacy", "host_addr")` — override the dict-walk path

To exclude a field from YAML resolution, pass `YamlSource` itself to
`opt(excluded_from=[YamlSource])`.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import dataclasses
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, ClassVar

import yaml

from confline.config.types import FieldPath
from confline.config.schema import ConfigFieldInfo, ConfigSchema
from confline.errors import (
    ConfigFileNotFoundError,
    YamlParseError,
    YamlPathCollisionError,
    YamlSchemaError,
    YamlSizeLimitError,
)
from confline.sources.base import (
    NO_VALUE,
    FileOrigin,
    Source,
)

_MISSING_KEY = object()


class YamlPath:
    """Override the dict-walk path for a field.

    Usage: `Annotated[str, YamlPath("legacy", "host_addr")]`.
    """

    def __init__(self, *parts: str) -> None:
        if not parts:
            raise ValueError("YamlPath requires at least one part")
        self.parts = tuple(parts)

    def __repr__(self) -> str:
        return f"YamlPath{self.parts!r}"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, YamlPath) and self.parts == other.parts

    def __hash__(self) -> int:
        return hash((type(self), self.parts))


class YamlSource(Source):
    """Resolve fields from a sequence of dict scopes.

    `scopes` is highest-priority-first. The first scope that contains
    the field's path wins; lower-priority scopes are not consulted for
    that field. `key: null` in YAML produces a real `None` value —
    only an *absent* key falls through.

    Per-field provenance is exposed via `describe_provenance(field)`
    when the source is built via `from_files()` — each scope keeps a
    pointer to the file it came from, so the renderer can name the
    actual file that supplied the field rather than the merged set.
    """

    name: ClassVar[str] = "yaml"
    display_label: ClassVar[str] = "yaml"
    display_kv_separator: ClassVar[str] = ": "

    # First-line DoS guard: refuse to parse files larger than this.
    # Override on a subclass when the app legitimately needs more.
    MAX_FILE_BYTES: ClassVar[int] = 10 * 1024 * 1024  # 10 MiB

    def __init__(
        self,
        scopes: Sequence[Mapping[str, Any]],
        *,
        files: Sequence["Path | FileOrigin"] = (),
    ) -> None:
        self._scopes = tuple(scopes)
        self._files: tuple[FileOrigin, ...] = tuple(
            f if isinstance(f, FileOrigin) else FileOrigin(path=f) for f in files
        )
        # Parallel to `_scopes`. `from_files()` populates with the
        # FileOrigin each scope came from; manual construction leaves
        # all entries `None`, so `describe_provenance` returns `None`
        # and the renderer falls back to `display_label`.
        self._scope_origins: tuple[FileOrigin | None, ...] = (None,) * len(self._scopes)

    def validate_schema(self, schema: ConfigSchema) -> None:
        seen: dict[FieldPath, str] = {}
        for full_path, field in _iter_fields_with_full_path(schema):
            view = dataclasses.replace(field, path=full_path)
            yaml_path = self._path_for(view)
            dotted = ".".join(full_path)
            previous = seen.get(yaml_path)
            if previous is not None and previous != dotted:
                raise YamlPathCollisionError(
                    path=".".join(yaml_path),
                    field_a=previous,
                    field_b=dotted,
                )
            seen[yaml_path] = dotted

    def resolve(self, field: ConfigFieldInfo) -> Any:
        path = self._path_for(field)
        for scope in self._scopes:
            value = _walk(scope, path)
            if value is _MISSING_KEY:
                continue
            return value
        return NO_VALUE

    def _describe_field(self, field: ConfigFieldInfo) -> str | None:
        return ".".join(self._path_for(field))

    def describe_provenance(self, field: ConfigFieldInfo) -> str | None:
        if not any(self._scope_origins):
            return None

        path = self._path_for(field)
        for scope, origin in zip(self._scopes, self._scope_origins, strict=True):
            if _walk(scope, path) is _MISSING_KEY:
                continue
            if origin is None:
                return None
            return f"{self.display_label} {origin.path}"
        return None

    def describe_unset_hint(self, key: str) -> str | None:
        return f" — remove {key}"

    def _path_for(self, field: ConfigFieldInfo) -> FieldPath:
        for m in field.annotated:
            if isinstance(m, YamlPath):
                return m.parts
        return field.path

    @classmethod
    def from_files(
        cls,
        paths: "Sequence[Path | FileOrigin]",
    ) -> "YamlSource":
        """Read YAML files in order, build a scope per file.

        Last file wins at each leaf — later paths in the sequence
        override earlier ones. Each path must exist; missing files
        raise `ConfigFileNotFoundError` rather than being silently
        skipped, so a typoed `--config /etc/myapp/typoo.yaml` cannot
        quietly fall through to defaults. Apps needing optional
        discovery filter the list to existing paths before calling.

        Entries can be bare `Path`s (origin defaults to `None`) or
        `FileOrigin(path, origin)` records. Origin labels are
        free-form metadata available to operator-facing diagnostics
        — they let downstream tooling tell apart files supplied via
        different channels.

        Each file becomes its own scope (no deep-merge), kept in
        highest-priority-first order internally so that `resolve()`
        finds the winning scope first and `describe_provenance`
        names the actual file that supplied the field.

        Apps needing plugin/command-scoped fallback (multiple
        distinct scopes) build their own factory; the per-file scope
        default covers the common case.
        """
        normalized: list[FileOrigin] = [
            p if isinstance(p, FileOrigin) else FileOrigin(path=p) for p in paths
        ]
        scopes_in_input_order: list[Mapping[str, Any]] = []
        for entry in normalized:
            scope = cls._read_one(entry.path)
            scopes_in_input_order.append(scope if scope is not None else {})

        # `_scopes` is highest-priority-first (last input file first);
        # `_files` keeps input order for display.
        instance = cls(
            scopes=list(reversed(scopes_in_input_order)),
            files=tuple(normalized),
        )
        instance._scope_origins = tuple(reversed(normalized))
        return instance

    @classmethod
    def _read_one(cls, path: Path) -> Mapping[str, Any] | None:
        """Read and validate a single YAML file. Returns the top-level
        mapping, or `None` for empty files."""
        if not path.exists():
            raise ConfigFileNotFoundError(path)

        size = path.stat().st_size
        if size > cls.MAX_FILE_BYTES:
            raise YamlSizeLimitError(path, size=size, limit=cls.MAX_FILE_BYTES)

        text = path.read_text(encoding="utf-8")
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            mark = getattr(exc, "problem_mark", None) or getattr(exc, "context_mark", None)
            line = (mark.line + 1) if mark is not None else None
            column = (mark.column + 1) if mark is not None else None
            detail = getattr(exc, "problem", None) or str(exc).splitlines()[0]
            raise YamlParseError(
                path,
                line=line,
                column=column,
                detail=detail,
            ) from exc

        if data is None:
            return None
        if not isinstance(data, Mapping):
            raise YamlSchemaError(
                path,
                reason=f"expected mapping at root, got {type(data).__name__}",
            )
        return data


def _iter_fields_with_full_path(
    schema: ConfigSchema,
    prefix: FieldPath = (),
) -> Iterable[tuple[FieldPath, ConfigFieldInfo]]:
    for field in schema.all_fields():
        full = prefix + field.path
        if YamlSource in field.excluded_from:
            continue
        if field.nested_schema is not None:
            yield from _iter_fields_with_full_path(field.nested_schema, full)
            continue
        yield full, field


def _walk(scope: Mapping[str, Any], path: FieldPath) -> Any:
    cursor: Any = scope
    for part in path:
        if not isinstance(cursor, Mapping) or part not in cursor:
            return _MISSING_KEY
        cursor = cursor[part]
    return cursor
