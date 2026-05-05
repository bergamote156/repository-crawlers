"""
Dataset input loader — JSON / JSONL → `list[OnedataDataset]`.

Pulled out of the planner so the CLI can load the file once and pass
the result into both the planner (needs count + first URL) and the
registration runner (iterates every dataset).
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import json
from pathlib import Path

from onedata_dataset import OnedataDataset


class DatasetsInputError(RuntimeError):
    """Input file is missing, malformed, or contains no usable records."""


def load_datasets(path: Path) -> list[OnedataDataset]:
    """Read every dataset from `path`. Detects format from the file extension.

    Raises `DatasetsInputError` for unreadable / malformed / empty input
    so the CLI can render a single failure mode regardless of source.
    """
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        return _read_jsonl(path)
    if suffix == ".json":
        return _read_json(path)
    raise DatasetsInputError(
        f"{path}: unsupported file extension {suffix!r}, use .json or .jsonl",
    )


def _read_jsonl(path: Path) -> list[OnedataDataset]:
    out: list[OnedataDataset] = []
    with path.open(encoding="utf-8") as f:
        for line_no, raw in enumerate(f, 1):
            line = raw.strip()
            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DatasetsInputError(
                    f"{path}: line {line_no}: invalid JSON ({exc.msg})",
                ) from exc

            out.append(_build_dataset(record, where=f"{path}: line {line_no}"))
    return out


def _read_json(path: Path) -> list[OnedataDataset]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DatasetsInputError(f"{path}: invalid JSON ({exc.msg})") from exc

    if isinstance(data, dict):
        records = [data]
    elif isinstance(data, list):
        records = data
    else:
        raise DatasetsInputError(f"{path}: top-level JSON must be an object or an array")

    return [
        _build_dataset(record, where=f"{path}: dataset #{idx}")
        for idx, record in enumerate(records, 1)
    ]


def _build_dataset(record: dict, *, where: str) -> OnedataDataset:
    """Convert a parsed JSON record to an `OnedataDataset`, contextualising shape errors."""
    try:
        return OnedataDataset.from_json(record)
    except (KeyError, TypeError) as exc:
        raise DatasetsInputError(f"{where}: invalid dataset record ({exc})") from exc
