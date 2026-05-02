"""
Default-value source — last in the chain.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import MISSING
from typing import Any, ClassVar

from confline.config.schema import ConfigFieldInfo
from confline.sources.base import NO_VALUE, Source


class DefaultSource(Source):
    """Returns the field's declared default. Skips fields with no default."""

    name: ClassVar[str] = "default"
    display_label: ClassVar[str] = "default"
    is_fallback: ClassVar[bool] = True

    def resolve(self, field: ConfigFieldInfo) -> Any:
        if field.default_factory is not None:
            return field.default_factory()
        if field.default is not MISSING:
            return field.default
        return NO_VALUE
