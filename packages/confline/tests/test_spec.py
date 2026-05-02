"""
Tests for the cross-cutting metadata module.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from confline.config.types import FieldPath


def test_field_path_is_tuple_of_str():
    path: FieldPath = ("db", "host")
    assert isinstance(path, tuple)
    assert all(isinstance(p, str) for p in path)
