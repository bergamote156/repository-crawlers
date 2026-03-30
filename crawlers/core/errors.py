"""Error/Failure handling utilities"""

from dataclasses import asdict, is_dataclass

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"


def to_json(err: object) -> dict:
    """Serialize any error to a JSON-safe dict.

    Supports:
    - dict: returned as-is
    - objects with to_json(): call it
    - dataclass instances: `asdict()` (nested dataclasses become nested dicts)
    - anything else: wrap in {"error": str(err)}
    """
    if isinstance(err, dict):
        return err
    if hasattr(err, "to_json"):
        return err.to_json()
    if is_dataclass(err) and not isinstance(err, type):
        return asdict(err)

    return {"error": str(err)}
