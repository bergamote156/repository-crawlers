"""
Public provenance API — `Provenance` record and `ConfigBase.source_of`.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import pytest

from confline import (
    CliSource,
    ConfigBase,
    DefaultSource,
    Provenance,
    YamlSource,
    load_config,
    opt,
)
from tests.helpers.fixtures import make_namespace


class DbCfg(ConfigBase):
    host: str = opt("localhost")
    port: int = opt(5432)


class AppCfg(ConfigBase):
    db: DbCfg = opt(default_factory=DbCfg)
    workers: int = opt(4)


def test_source_of_returns_provenance_record_for_yaml_field(tmp_path):
    cfg_file = tmp_path / "app.yaml"
    cfg_file.write_text("workers: 8\n", encoding="utf-8")
    cfg = load_config(
        AppCfg,
        sources=[YamlSource.from_files([cfg_file]), DefaultSource()],
    )

    prov = cfg.source_of("workers")

    assert isinstance(prov, Provenance)
    assert prov.name == "yaml"
    assert prov.label.startswith("yaml ")
    assert str(cfg_file) in prov.label


def test_source_of_returns_default_for_unset_field():
    cfg = load_config(AppCfg, sources=[DefaultSource()])

    assert cfg.source_of("workers") == Provenance(name="default", label="default")


def test_provenance_is_attached_for_every_resolved_field():
    """The resolver stamps provenance per-field — including fields that
    fell through to `DefaultSource`. `source_of` must answer for every
    leaf path, not only ones that a higher-priority source touched."""
    cfg = load_config(
        AppCfg,
        sources=[
            YamlSource(scopes=[{"db": {"host": "h"}}]),
            DefaultSource(),
        ],
    )
    assert cfg.source_of("db.host").name == "yaml"
    assert cfg.source_of("db.port").name == "default"
    assert cfg.source_of("workers").name == "default"


def test_source_of_accepts_tuple_path_for_nested_field():
    cfg = load_config(
        AppCfg,
        sources=[
            YamlSource(scopes=[{"db": {"host": "h"}}]),
            DefaultSource(),
        ],
    )

    by_dotted = cfg.source_of("db.host")
    by_tuple = cfg.source_of(("db", "host"))

    assert by_dotted == by_tuple
    assert by_dotted.name == "yaml"


def test_source_of_raises_keyerror_for_unknown_path():
    cfg = load_config(AppCfg, sources=[DefaultSource()])

    with pytest.raises(KeyError):
        cfg.source_of("nope.does_not_exist")


def test_source_of_argparse_field_uses_canonical_identity():
    cfg = load_config(
        AppCfg,
        sources=[
            CliSource(make_namespace(workers=12)),
            DefaultSource(),
        ],
    )

    prov = cfg.source_of("workers")

    assert prov.name == "argparse"
    assert prov.label == "command line"


def test_source_of_on_nested_raises_with_hint():
    """Provenance is stamped on the root config — calling source_of on
    a nested ConfigBase instance reached via attribute walk silently
    invokes the inherited method and used to give a bare KeyError. The
    operator should see why and how to fix it."""
    cfg = load_config(
        AppCfg,
        sources=[
            YamlSource(scopes=[{"db": {"host": "h"}}]),
            DefaultSource(),
        ],
    )

    with pytest.raises(KeyError) as exc:
        cfg.db.source_of("host")

    msg = str(exc.value)
    assert "root" in msg
    assert "db.host" in msg


def test_source_of_on_hand_built_instance_raises_with_hint():
    """A ConfigBase instantiated by hand (not via load_config) carries
    no provenance. Distinct hint from the nested case so the developer
    knows it isn't 'wrong instance' but 'wrong constructor'."""
    cfg = AppCfg()  # bypass load_config — provenance never stamped

    with pytest.raises(KeyError) as exc:
        cfg.source_of("workers")

    msg = str(exc.value)
    assert "load_config" in msg


def test_provenance_record_is_frozen():
    prov = Provenance(name="yaml", label="yaml /etc/app.yaml")
    with pytest.raises(Exception):  # noqa: BLE001 — dataclass-frozen raises FrozenInstanceError or AttributeError depending on slots.
        prov.name = "argparse"  # type: ignore[misc]


def test_describe_provenance_failure_falls_back_to_display_label(caplog):
    """A custom source whose `describe_provenance` raises must not crash
    resolution; the renderer falls back to `source.display_label`. With
    DEBUG enabled on the `confline` logger, the operator sees the stack —
    the bug is observable but not fatal. Asserting on `display_label` (not
    `name`) because the fallback returns operator-facing rendering; leaking
    the wire-id here would re-introduce the same class of bug as
    `help_format.py`."""
    import logging

    from confline.sources.base import Source

    class _BuggySource(Source):
        name = "buggy"
        display_label = "buggy vault"

        def resolve(self, field):  # noqa: ARG002
            return "value-from-buggy"

        def describe_provenance(self, field):  # noqa: ARG002
            raise RuntimeError("bug in describe_provenance")

    class Cfg(ConfigBase):
        host: str = opt("default")

    with caplog.at_level(logging.DEBUG, logger="confline"):
        cfg = load_config(Cfg, sources=[_BuggySource(), DefaultSource()])

    assert cfg.host == "value-from-buggy"
    assert cfg.source_of("host").label == "buggy vault"
    matching = [
        r for r in caplog.records
        if r.name == "confline" and "describe_provenance failed" in r.getMessage()
    ]
    assert matching, "expected DEBUG log naming the failed describe_provenance"
    assert matching[0].exc_info is not None
