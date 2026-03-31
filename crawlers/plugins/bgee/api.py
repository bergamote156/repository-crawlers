"""Bgee API Client - schema.org JSON-LD harvesting."""

__author__ = "Vincent Emonet"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import dataclass
from typing import AsyncIterator
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from rdflib import Dataset, Namespace
from rdflib.namespace import RDF
from rdflib.term import Node

from crawlers.core.abc.api import ApiClient
from crawlers.core.ui import console
from crawlers.plugins.bgee.models import BgeeRawRecord

# Support both https and http schema.org namespace variants
_SDO = (Namespace("https://schema.org/"), Namespace("http://schema.org/"))


def _vals(g: Dataset, subject: Node, prop: str) -> list[str]:
    """All string values for `schema:prop` on subject, deduplicated across both SDO namespaces."""
    seen: dict[str, None] = {}
    for ns in _SDO:
        for obj in g.objects(subject, ns[prop]):
            seen[str(obj)] = None
    return list(seen.keys())


def _val(g: Dataset, subject: Node, prop: str) -> str | None:
    """First string value for `schema:prop` on subject."""
    vals = _vals(g, subject, prop)
    return vals[0] if vals else None


def _top_level_datasets(g: Dataset) -> list[Node]:
    """`Dataset` nodes that are not `hasPart` children of another `Dataset`."""
    all_ds: set[Node] = {s for ns in _SDO for s in g.subjects(RDF.type, ns["Dataset"])}
    children: set[Node] = {
        child
        for ns in _SDO
        for parent in all_ds
        for child in g.objects(parent, ns["hasPart"])
        if child in all_ds
    }
    return [ds for ds in all_ds if ds not in children]


@dataclass
class BgeeIteratorOpts:
    """Options for Bgee dataset iteration."""

    start_url: str
    max_records: int | None = None


class BgeeClient(ApiClient[BgeeIteratorOpts, BgeeRawRecord]):
    """
    Crawls Bgee species pages and extracts schema.org JSON-LD Dataset records.

    Starting from a species listing page, follows data-discover links to individual
    species pages, then parses JSON-LD from each page using rdflib.
    """

    # pylint: disable=invalid-overridden-method
    async def iterate_datasets(self, opts: BgeeIteratorOpts) -> AsyncIterator[BgeeRawRecord]:
        """Iterate over Bgee dataset records extracted from species pages.

        Fetches the start URL, discovers species page links, and yields
        `BgeeRawRecord` for each `schema:Dataset` found.
        """
        yielded = 0
        try:
            async with self.session.get(opts.start_url) as resp:
                resp.raise_for_status()
                html = await resp.text()
        except Exception as e:  # pylint: disable=broad-except
            console.error(f"Failed to fetch start URL {opts.start_url}: {e}")
            return
        _, discover_urls = self._parse_page(html, opts.start_url)
        console.info(f"Found {len(discover_urls)} pages to crawl")
        for url in discover_urls:
            if opts.max_records is not None and yielded >= opts.max_records:
                break
            try:
                async with self.session.get(url) as resp:
                    resp.raise_for_status()
                    page_html = await resp.text()
            except Exception as e:  # pylint: disable=broad-except
                console.warning(f"Failed to fetch {url}: {e}")
                continue
            records, _ = self._parse_page(page_html, url)
            console.debug(f"Found {len(records)} dataset(s) on {url}")
            for record in records:
                yield record
                yielded += 1
                if opts.max_records is not None and yielded >= opts.max_records:
                    return
        console.info(f"Total datasets extracted: {yielded}")

    def _parse_page(
        self, html: str, page_url: str
    ) -> tuple[list[BgeeRawRecord], list[str]]:
        """Parse a page's JSON-LD and discover links.

        Loads all JSON-LD <script> blocks from the page into a single rdflib Dataset,
        then finds top-level schema:Dataset nodes.

        Returns:
            (records, discover_urls) where discover_urls are data-discover link targets.
        """
        soup = BeautifulSoup(html, "lxml")
        discover_urls = [
            urljoin(page_url, str(a["href"]))
            for a in soup.find_all("a", attrs={"data-discover": "true", "href": True})
        ]
        scripts = soup.find_all("script", type="application/ld+json")
        if not scripts:
            return [], discover_urls

        # Load all JSON-LD scripts from the page into one Dataset for cross-reference support
        g = Dataset()
        raw_parts: list[str] = []
        for script in scripts:
            raw_json = script.string
            if not raw_json:
                continue
            raw_parts.append(raw_json)
            try:
                g.parse(data=raw_json, format="json-ld")
            except Exception as e:  # pylint: disable=broad-except
                console.warning(f"Failed to parse JSON-LD on {page_url}: {e}")

        combined_raw = "\n".join(raw_parts)
        top_datasets = _top_level_datasets(g)
        records = [
            BgeeRawRecord(raw=combined_raw, graph=g, node=ds_node)
            for ds_node in top_datasets
        ]
        return records, discover_urls
