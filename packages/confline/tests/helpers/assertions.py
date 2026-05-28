"""
Custom assertions used across the test suite.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from confline.config.base import ConfigBase


def assert_field_resolved_from(
    config: ConfigBase,
    dotted_path: str,
    expected_source: str,
) -> None:
    """Assert `config` resolved `dotted_path` from `expected_source`."""
    try:
        actual = config.source_of(dotted_path).name
    except KeyError:
        actual = None
    assert actual == expected_source, (
        f"expected field {dotted_path!r} from source {expected_source!r}, got {actual!r}"
    )
