"""Bgee Parser - converts schema.org JSON-LD records to BgeeDataset."""

__author__ = "Vincent Emonet"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from crawlers.core.processors.parsers import Parser
from crawlers.core.ui import console
from crawlers.plugins.bgee.api import _SDO, _val
from crawlers.plugins.bgee.models import BgeeDataset, BgeeFile, BgeeRawRecord


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
        # Also collect files from hasPart nested datasets
        for ns in _SDO:
            for part in g.objects(node, ns["hasPart"]):
                files.extend(self._extract_files(g, part))
        if not files:
            console.debug(f"Skipping {identifier}: no downloadable files found")
            return None

        return BgeeDataset(
            identifier=identifier,
            title=title,
            files=files,
            description=_val(g, node, "description"),
            datetime=_val(g, node, "dateModified") or _val(g, node, "datePublished"),
            self_link=identifier,
            _raw=raw,
        )

    def _extract_files(self, g, node) -> list[BgeeFile]:
        """Extract downloadable files from a schema:Dataset node."""
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
