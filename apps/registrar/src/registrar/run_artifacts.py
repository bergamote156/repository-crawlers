"""Per-run artifact directory management."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import json
import pathlib
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import yaml

from confline import ConfigBase
from registrar.register.types import Summary


class _YamlDumper(yaml.Dumper):
    pass


_YamlDumper.add_multi_representer(
    pathlib.PurePath,
    lambda d, v: d.represent_scalar("tag:yaml.org,2002:str", str(v)),
)


def create_run_dir(output_dir: Path) -> Path:
    """Create and return a timestamped run directory under `output_dir/runs/`."""
    now = datetime.now(tz=UTC)
    dirname = now.strftime("%Y-%m-%dT%H-%M-%S") + "_register"
    run_dir = output_dir / "runs" / dirname
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def dump_config(run_dir: Path, config: ConfigBase) -> None:
    """Write the effective config as YAML into the run dir."""
    path = run_dir / "config.yaml"
    with path.open("w") as f:
        yaml.dump(
            asdict(config),  # type: ignore[call-overload]  # subclasses are always dataclasses
            f,
            Dumper=_YamlDumper,
            default_flow_style=False,
            sort_keys=False,
        )


def dump_summary(run_dir: Path, summary: Summary) -> None:
    """Write `summary.json` — the machine-readable post-mortem."""
    path = run_dir / "summary.json"
    with path.open("w") as f:
        json.dump(asdict(summary), f, indent=2, default=str)
