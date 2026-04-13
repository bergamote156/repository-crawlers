"""TopAnat data models — config, seed entries, parsed dataset carrier."""

# pylint: disable=too-few-public-methods

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from crawlers.core import ConfigBase, CrawlConfig, HttpConfig, opt
from crawlers.metadata.datacite import DataCiteRecord

# Path to the bundled seed list, resolved at import time so the plugin works
# regardless of the caller's CWD.
DEFAULT_SEEDS_PATH = Path(__file__).parent / "seeds.yaml"


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────


class TopanatApiConfig(HttpConfig):
    """Base configuration for the EBI APIs used by the TopAnat plugin."""

    base_url: str = opt(
        "https://www.ebi.ac.uk",
        description="EBI base URL — GWAS REST and OLS both live under this host",
    )


class TopanatSeedsConfig(ConfigBase):
    """Holds just the path to the seed list — shared between crawl and list-seeds."""

    seeds: str = opt(
        str(DEFAULT_SEEDS_PATH),
        description="Path to the YAML file listing entries to onboard",
    )


class TopanatCrawlConfig(TopanatApiConfig, TopanatSeedsConfig, CrawlConfig, kw_only=True):
    """
    Full crawl configuration for the TopAnat plugin.

    `no_url_validation` defaults to True here because the two "files" of every
    dataset are dynamic GWAS API queries (15s+ to materialize). Probing them
    on every crawl serves no purpose and would burn the EBI rate budget.
    """

    no_url_validation: bool = opt(
        True,
        description="Disable HEAD-probe URL validation during parse",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Seed entries
# ─────────────────────────────────────────────────────────────────────────────

TopanatEntryKind = Literal["trait", "publication"]


@dataclass(frozen=True)
class TopanatEntry:
    """A single seeded item to onboard: an EFO/MONDO trait or a PubMed publication."""

    kind: TopanatEntryKind
    id: str  # noqa: A003 — short form (e.g. "EFO_0003924") or PubMed ID


# ─────────────────────────────────────────────────────────────────────────────
# Parser carrier
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ParsedTopanatRecord:
    """Result of converting a fetched trait/publication into a registrable shape."""

    identifier: str  # the canonical web URL — used as both `pid` and DataCite identifier
    title: str
    metadata: DataCiteRecord
    json_url: str
    tsv_url: str
