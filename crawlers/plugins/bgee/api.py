"""Bgee API - RDF helpers, parser, and HTTP client."""

__author__ = "Vincent Emonet"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import json
from dataclasses import dataclass
from typing import AsyncIterator
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from rdflib import Dataset, Namespace
from rdflib.namespace import RDF
from rdflib.term import Node

from crawlers.core.abc.api import ApiClient
from crawlers.core.processors.parsers import Parser
from crawlers.core.ui import console
from crawlers.plugins.bgee.models import BgeeDataset, BgeeFile, BgeeRawRecord


# --- Client ---

@dataclass
class BgeeIteratorOpts:
    """Options for Bgee dataset iteration."""

    start_url: str
    max_records: int | None = None


class BgeeClient(ApiClient[BgeeIteratorOpts, BgeeRawRecord]):
    """Crawls Bgee species pages and extracts schema.org JSON-LD Dataset records."""

    # pylint: disable=invalid-overridden-method
    async def iterate_datasets(self, opts: BgeeIteratorOpts) -> AsyncIterator[BgeeRawRecord]:
        """Fetch start URL, discover species page links, yield `BgeeRawRecord` per dataset."""
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

    def _parse_page(self, html: str, page_url: str) -> tuple[list[BgeeRawRecord], list[str]]:
        """Load all JSON-LD from a page into one rdflib Dataset, return records + discover links."""
        soup = BeautifulSoup(html, "lxml")
        discover_urls = [
            urljoin(page_url, str(a["href"]))
            for a in soup.find_all("a", attrs={"data-discover": "true", "href": True})
        ]
        scripts = soup.find_all("script", type="application/ld+json")
        if not scripts:
            return [], discover_urls

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

        records = [
            BgeeRawRecord(raw="\n".join(raw_parts), graph=g, node=ds_node)
            for ds_node in _top_level_datasets(g)
        ]
        return records, discover_urls


# --- Parser ---

class BgeeParser(Parser[BgeeRawRecord, BgeeDataset]):
    """Converts a `BgeeRawRecord` (rdflib graph + node) into a `BgeeDataset`."""

    def parse(self, raw: BgeeRawRecord) -> BgeeDataset | None:  # noqa: A002
        """Parse `schema:Dataset` record from rdflib graph."""
        g = raw.graph
        node = raw.node
        identifier = _val(g, node, "url") or str(node)
        title = _val(g, node, "name") or ""
        if not identifier or not title:
            console.warning(f"Skipping Bgee record missing identifier or title: {node}")
            return None

        files = self._extract_files(g, node)
        for ns in _SDO:
            for part in g.objects(node, ns["hasPart"]):
                files.extend(self._extract_files(g, part))
        if not files:
            console.debug(f"Skipping {identifier}: no downloadable files found")
            return None

        keywords = _vals(g, node, "keywords")
        # schema:citation may be plain DOI URLs or JSON-encoded arrays (Bgee quirk)
        citations: list[str] = []
        for raw_citation in _vals(g, node, "citation"):
            try:
                parsed = json.loads(raw_citation)
                citations.extend(parsed) if isinstance(parsed, list) else citations.append(raw_citation)
            except (json.JSONDecodeError, ValueError):
                citations.append(raw_citation)

        return BgeeDataset(
            identifier=identifier,
            title=title,
            files=files,
            description=_val(g, node, "description"),
            datetime=_val(g, node, "dateModified") or _val(g, node, "datePublished"),
            self_link=identifier,
            keywords=keywords,
            citations=citations,
            _raw=raw,
        )

    def _extract_files(self, g: Dataset, node: Node) -> list[BgeeFile]:
        """Extract downloadable files from a `schema:Dataset` node."""
        files: list[BgeeFile] = []
        seen_urls: set[str] = set()
        for ns in _SDO:
            for dist in g.objects(node, ns["distribution"]):
                url = (
                    _val(g, dist, "contentUrl")
                    or _val(g, dist, "downloadURL")
                    or _val(g, dist, "url")
                    or (str(dist) if str(dist).startswith("http") else None)
                )
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                name = _val(g, dist, "name") or url.split("/")[-1].split("?")[0]
                files.append(BgeeFile(name=name, url=url))
        return files


# --- RDF helpers ---

_SDO = (Namespace("https://schema.org/"), Namespace("http://schema.org/"))
"""Support both https and http schema.org namespace variants."""

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
