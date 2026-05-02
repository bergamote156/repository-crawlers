"""
Threaded resolution context — the source chain plus safe-describe helpers.

Many resolution helpers need the same handful of inputs (the active source
chain, the failing field, the source instance under question) plus the
same defensive try/except wrapper around source-side label calls.
`ResolutionContext` holds the source chain; the module-level helpers hold
the eligibility check and the safe-describe pattern in one place so call
sites in resolver, error-record builder, and mutex enforcement stop
repeating the boilerplate.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import logging
from dataclasses import dataclass

from confline.config.schema import ConfigFieldInfo
from confline.sources.base import Source

logger = logging.getLogger("confline")


@dataclass(frozen=True, slots=True)
class ResolutionContext:
    """Immutable snapshot of the source chain for a single load_config call.

    Threaded into resolver helpers, error-record builders, and mutex
    enforcement so each can ask cross-source questions ("which other
    sources can name this field?", "what's the source-native key for
    this provider?") without re-deriving the chain.
    """

    sources: tuple[Source, ...]


def is_source_eligible(field: ConfigFieldInfo, source: Source) -> bool:
    """Return True when this source can be asked to resolve this field.

    `excluded_from` is the user-side opt-out (per field). `supports_field`
    is the source-side capability declaration (e.g. argparse refuses
    `list[ConfigBase]`). Centralised so the resolver and the suggestion
    builder stay in lock-step on the rules.
    """
    if type(source) in field.excluded_from:
        return False

    return type(source).supports_field(field)


def safe_describe_field(source: Source, field: ConfigFieldInfo) -> str | None:
    """`source.describe_field(field)` with defensive try/except.

    Source-side label calls are best-effort — never break resolution or
    error rendering over a buggy implementation. Logs at DEBUG with full
    stack info so anyone diagnosing a third-party source can flip the
    level and see the real failure.
    """
    try:
        return source.describe_field(field)
    except Exception:  # noqa: BLE001 — never crash on a label call
        logger.debug(
            "describe_field failed for source %r on field %r",
            source.name, ".".join(field.path), exc_info=True,
        )
        return None


def safe_describe_provenance(source: Source, field: ConfigFieldInfo) -> str:
    """Return per-field provenance label, falling back to `source.display_label`.

    The base contract for `describe_provenance` is `str | None` — `None`
    means "no per-instance info, use the class label". A buggy
    implementation that raises is treated the same way; provenance
    labels are helpful metadata, not a reason to abort resolution.
    """
    try:
        result = source.describe_provenance(field)
    except Exception:  # noqa: BLE001 — never crash on a label call
        logger.debug(
            "describe_provenance failed for source %r on field %r",
            source.name, ".".join(field.path), exc_info=True,
        )
        return source.display_label

    if result is None:
        return source.display_label

    return result
