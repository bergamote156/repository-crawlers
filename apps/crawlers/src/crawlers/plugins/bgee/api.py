"""Bgee API - RDF helpers, parser, and HTTP client."""

__author__ = "Vincent Emonet"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import json
from collections.abc import AsyncIterator
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from rdflib import Dataset, Namespace
from rdflib.namespace import RDF
from rdflib.term import Node

from crawlers.core import Err, HttpClient, Ok
from crawlers.metadata.datacite import (
    Creator,
    DataCiteRecord,
    Date,
    DateType,
    Description,
    IdentifierType,
    NameIdentifier,
    NameType,
    RelatedIdentifier,
    RelatedIdentifierType,
    RelationType,
    Rights,
)
from crawlers.model import OnedataDataset, OnedataFile
from crawlers.plugins.bgee.models import (
    BgeeIteratorOpts,
    BgeeRawRecord,
)
from crawlers.plugins.utils.datetime import year_from_iso
from crawlers.ui import console

# Bgee defaults — moved here from the legacy BgeeDataCiteBuilder.
_BGEE_PUBLISHER = "Bgee"
_BGEE_DEFAULT_CREATOR_NAME = "Bgee"
_BGEE_DEFAULT_SUBJECTS = [
    "gene expression",
    "Bgee",
    "genomics",
    "transcriptomics",
]
_BGEE_RIGHTS = Rights(text="CC0 1.0 Universal (CC0 1.0) Public Domain Dedication")
_BGEE_RESOURCE_TYPE_VALUE = "Gene expression data"


class BgeeClient:
    """
    Stateless façade over `HttpClient` that crawls Bgee species pages
    and extracts schema.org JSON-LD Dataset records.
    """

    def __init__(self, http: HttpClient):
        self._http = http

    async def iterate_datasets(self, opts: BgeeIteratorOpts) -> AsyncIterator[BgeeRawRecord]:
        """Fetch start URL, discover species page links, yield `BgeeRawRecord` per dataset."""
        yielded = 0
        start_result = await self._http.get_text(opts.start_url)
        if isinstance(start_result, Err):
            console.error(f"Failed to fetch start URL {opts.start_url}: {start_result.value}")
            return
        _, discover_urls = self._parse_page(start_result.value, opts.start_url)
        console.info(f"Found {len(discover_urls)} pages to crawl")
        for url in discover_urls:
            if opts.max_records is not None and yielded >= opts.max_records:
                break
            page_result = await self._http.get_text(url)
            if isinstance(page_result, Err):
                console.warning(f"Failed to fetch {url}: {page_result.value}")
                continue
            records, _ = self._parse_page(page_result.value, url)
            console.debug(f"Found {len(records)} dataset(s) on {url}")
            for record in records:
                yield record
                yielded += 1
                if opts.max_records is not None and yielded >= opts.max_records:
                    return
        console.info(f"Total datasets extracted: {yielded}")

    def _parse_page(self, html: str, page_url: str) -> tuple[list[BgeeRawRecord], list[str]]:
        """Load JSON-LD into one rdflib Dataset; return records and discover URLs."""
        soup = BeautifulSoup(html, "html.parser")
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
            except Exception as e:
                console.warning(f"Failed to parse JSON-LD on {page_url}: {e}")

        records = [
            BgeeRawRecord(raw="\n".join(raw_parts), graph=g, node=ds_node)
            for ds_node in _top_level_datasets(g)
        ]
        return records, discover_urls


class BgeeParser:
    """Converts a `BgeeRawRecord` (rdflib graph + node) into an `OnedataDataset`."""

    def parse(self, raw: BgeeRawRecord) -> Ok[OnedataDataset] | None:  # noqa: A002
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
                if isinstance(parsed, list):
                    citations.extend(parsed)
                else:
                    citations.append(raw_citation)
            except (json.JSONDecodeError, ValueError):
                citations.append(raw_citation)

        creator_name = creator_url = None
        for ns in _SDO:
            for creator_node in g.objects(node, ns["creator"]):
                creator_name = creator_name or _val(g, creator_node, "name")
                creator_url = creator_url or _val(g, creator_node, "url")

        description = _val(g, node, "description")
        dt = _val(g, node, "dateModified") or _val(g, node, "datePublished")
        version = _val(g, node, "version")

        record = DataCiteRecord(
            identifier=identifier,
            identifier_type=IdentifierType.URL,
            creators=[_build_creator(creator_name, creator_url)],
            title=title,
            publisher=_BGEE_PUBLISHER,
            publication_year=year_from_iso(dt),
            resource_type_general="Dataset",
            resource_type_value=_BGEE_RESOURCE_TYPE_VALUE,
            subjects=keywords or list(_BGEE_DEFAULT_SUBJECTS),
            dates=[Date(value=dt, date_type=DateType.UPDATED)] if dt else [],
            descriptions=([Description(value=description)] if description else []),
            related_identifiers=_citations_to_related_identifiers(citations),
            rights_list=[_BGEE_RIGHTS],
            version=version,
        )

        return Ok(
            OnedataDataset(
                name=title,
                target_dir=title.replace("/", "-"),
                pid=identifier,
                metadata_xml=record.to_xml(),
                files=tuple(files),
            )
        )

    def _extract_files(self, g: Dataset, node: Node) -> list[OnedataFile]:
        """Extract downloadable files from a `schema:Dataset` node."""
        files: list[OnedataFile] = []
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
                name = _val(g, dist, "name") or url.rsplit("/", maxsplit=1)[-1].split("?")[0]
                files.append(OnedataFile(path=name, url=url))
        return files


# DataCite mapping helpers


def _build_creator(name: str | None, url: str | None) -> Creator:
    """Build the DataCite creator entry, falling back to the Bgee default."""
    return Creator(
        name=name or _BGEE_DEFAULT_CREATOR_NAME,
        name_type=NameType.ORGANIZATIONAL,
        identifiers=[NameIdentifier(value=url, scheme="URL")] if url else [],
    )


def _citations_to_related_identifiers(
    citations: list[str],
) -> list[RelatedIdentifier]:
    """Convert citation strings (DOI URLs or other URLs) to relatedIdentifier entries."""
    entries: list[RelatedIdentifier] = []
    for citation in citations:
        if "doi.org" in citation:
            entries.append(
                RelatedIdentifier(
                    value=citation.split("doi.org/", 1)[-1],
                    identifier_type=RelatedIdentifierType.DOI,
                    relation_type=RelationType.IS_REFERENCED_BY,
                )
            )
        else:
            entries.append(
                RelatedIdentifier(
                    value=citation,
                    identifier_type=RelatedIdentifierType.URL,
                    relation_type=RelationType.IS_REFERENCED_BY,
                )
            )
    return entries


# RDF helpers
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
