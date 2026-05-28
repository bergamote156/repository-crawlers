"""Post-resolution mutex group enforcement.

Runs after all validators so that `@model_validator` can reconcile
an apparent conflict before the check fires. The key semantic:
values from fallback sources (`DefaultSource.is_fallback = True`)
don't count as "user-provided" — two mutex fields both falling
through to their declared defaults is fine; two set explicitly via
different sources (env + YAML, CLI + env, etc.) is a violation.
This catches the cross-source case argparse's own mutually-exclusive
groups miss, since argparse only sees CLI flags.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import dataclasses
from typing import Any

from confline.config.base import ConfigBase
from confline.config.schema import ConfigFieldInfo, ConfigGroup, ConfigSchema
from confline.config.types import SECRET_PLACEHOLDER, FieldPath, Provenance
from confline.errors import MutexViolationError, ProvidedField
from confline.resolution.context import ResolutionContext, safe_describe_field
from confline.sources.base import Source


def enforce_mutex_groups(
    instance: ConfigBase,
    provenance: dict[FieldPath, Provenance],
    context: ResolutionContext,
) -> None:
    """Walk the config tree and raise on any mutex-group violation.

    Public entry point for the resolver. Wraps the `MutexEnforcer` —
    callers don't see the class because the only thing they need is
    "check this instance and its sub-instances".
    """
    MutexEnforcer(instance, provenance, context).check()


class MutexEnforcer:
    """Counts user-provided fields per mutex group across the schema tree.

    NOTE: "user-provided" means provenance points to a non-fallback source.
    `DefaultSource.is_fallback = True` excludes declared defaults from the
    count. This catches the cross-source case argparse's own check misses:
    a YAML file setting both `json: true` and `yaml: true` registers no CLI
    flag, so argparse never sees the conflict. The post-resolution check
    fires after every `@model_validator` has had a chance to fix things up.

    Lookups (`sources_by_name`, `fallback_names`, `schema_fields`) are
    pre-computed once in `__init__` so the recursion is a pure tree walk.
    """

    def __init__(
        self,
        root: ConfigBase,
        provenance: dict[FieldPath, Provenance],
        context: ResolutionContext,
    ) -> None:
        self._root = root
        self._provenance = provenance
        self._sources_by_name: dict[str, Source] = {s.name: s for s in context.sources}
        self._fallback_names: frozenset[str] = frozenset(
            s.name for s in context.sources if s.is_fallback
        )
        self._schema_fields: dict[str, ConfigFieldInfo] = _flatten_schema(root)

    # --- Walk ---

    def check(self) -> None:
        """Run mutex enforcement starting at the root."""
        self._walk(self._root, type(self._root).__config_schema__, prefix=())

    def _walk(self, instance: ConfigBase, schema: ConfigSchema, *, prefix: FieldPath) -> None:
        for group in schema.groups:
            if group.is_mutex:
                self._enforce_group(group, prefix=prefix)

            for field in group.fields:
                if field.nested_schema is None:
                    continue

                self._walk(
                    getattr(instance, field.name),
                    field.nested_schema,
                    prefix=prefix + field.path,
                )

    # --- Per-group enforcement ---

    def _enforce_group(self, group: ConfigGroup, *, prefix: FieldPath) -> None:
        paths = [prefix + f.path for f in group.fields]
        names = [".".join(p) for p in paths]
        user_provided = [p for p in paths if self._is_user_provided(p)]

        if group.mutex_required and len(user_provided) != 1:
            raise MutexViolationError(
                group_name=group.name,
                field_paths=names,
                provided=[self._build_provided_field(p) for p in user_provided],
                required=True,
            )
        if not group.mutex_required and len(user_provided) > 1:
            raise MutexViolationError(
                group_name=group.name,
                field_paths=names,
                provided=[self._build_provided_field(p) for p in user_provided],
                required=False,
            )

    def _is_user_provided(self, path: FieldPath) -> bool:
        prov = self._provenance.get(path)
        if prov is None:
            return False
        return prov.name not in self._fallback_names

    # --- Provider record assembly ---

    def _build_provided_field(self, path: FieldPath) -> ProvidedField:
        """Resolve everything `format_mutex_error` needs about one provider.

        Pulls the live value from the root, redacts secret fields, asks the
        originating source for its native key form (so the renderer can
        print `--port`/`MYAPP_SOCKET`/`db.host` rather than the dotted path).
        """
        dotted = ".".join(path)
        prov = self._provenance.get(path)
        # `prov is None` only reachable if a caller hands us a path that
        # wasn't resolved — `_is_user_provided` already filters None.
        # Kept as a safety net so this method stays callable in isolation
        # (tests, future debug callers).
        source_name = prov.name if prov is not None else ""
        source_label = prov.label if prov is not None else source_name

        field = self._schema_fields.get(dotted)
        secret = field is not None and field.secret
        raw_value = _value_at_path(self._root, path)
        value: Any = SECRET_PLACEHOLDER if secret else raw_value

        source = self._sources_by_name.get(source_name)
        key: str | None = None
        if source is not None and field is not None:
            key = safe_describe_field(source, field)

        return ProvidedField(
            path=dotted,
            source_name=source_name,
            source_label=source_label,
            value=value,
            source_native_key=key,
            secret=secret,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Free helpers — pure tree walks without enforcer state
# ─────────────────────────────────────────────────────────────────────────────


def _flatten_schema(root: ConfigBase) -> dict[str, ConfigFieldInfo]:
    """Build `dotted_path -> ConfigFieldInfo` for the whole config tree.

    Computed once per enforcement run; the walker reads it for secret
    flags and source-native key lookup without re-traversing the schema.
    """
    schema = type(root).__config_schema__
    out: dict[str, ConfigFieldInfo] = {}

    def walk(s: ConfigSchema, prefix: FieldPath) -> None:
        for f in s.all_fields():
            full = prefix + f.path
            out[".".join(full)] = dataclasses.replace(f, path=full)
            if f.nested_schema is not None:
                walk(f.nested_schema, full)

    walk(schema, ())
    return out


def _value_at_path(config: ConfigBase, path: FieldPath) -> Any:
    """Return the value at the dotted path, or None if any node along the way is None.

    The early-return on None covers `Optional[NestedConfig]` set to None
    (the leaf can't be reached). For mutex enforcement this collapses to
    "the field was effectively unset" — which is fine: if a path led to
    a None nested config, that path's leaf cannot be claiming mutex.
    """
    cur: Any = config
    for part in path:
        cur = getattr(cur, part, None)
        if cur is None:
            return None
    return cur
