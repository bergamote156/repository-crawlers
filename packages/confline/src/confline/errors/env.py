"""
Environment-source schema validation errors.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from confline.errors.base import ConfigError


class EnvKeyCollisionError(ConfigError):
    """Two fields derive the same env-var name under the active EnvSource.

    - `key` — the derived env-var name that collided.
    - `field_a`, `field_b` — dotted schema paths; shown in the message so the
      schema author can disambiguate aliases, delimiters, or field names.
    """

    def __init__(
        self,
        *,
        key: str,
        field_a: str,
        field_b: str,
    ) -> None:
        self.source_native_key = key
        self.field_a = field_a
        self.field_b = field_b

        super().__init__(
            f"env var name collision: fields {field_a!r} and {field_b!r} both "
            f"map to {key!r}\n"
            f"\n"
            f"Resolve by:\n"
            f"  - change EnvSource(delimiter=...) to disambiguate, or\n"
            f"  - add EnvAlias('NEW_NAME') on one of the fields, or\n"
            f"  - rename one of the fields.",
        )
