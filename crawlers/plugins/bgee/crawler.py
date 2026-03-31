"""Bgee Crawler and DataCite metadata builder."""

__author__ = "Vincent Emonet"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, AsyncIterable, cast
from xml.dom import minidom

from crawlers.core.abc.api import ApiClient
from crawlers.core.crawler import BaseCrawler
from crawlers.core.metadata.datacite import DataCiteBuilder, DataCiteContext
from crawlers.core.processors.converters import OnedataConverter
from crawlers.core.processors.parsers import ParserProcessor
from crawlers.core.processors.pipeline import ProcessorPipeline
from crawlers.core.processors.writers import JSONLWriter
from crawlers.core.ui import console
from crawlers.plugins.bgee.api import BgeeClient, BgeeParser
from crawlers.plugins.bgee.models import BgeeCrawlConfig, BgeeIteratorOpts


class BgeeCrawler(BaseCrawler[BgeeCrawlConfig]):
    """Crawls Bgee species pages extracting schema.org JSON-LD dataset records."""

    def __init__(self, config: BgeeCrawlConfig):
        super().__init__(config)
        output_dir = Path(config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        self._raw_output_path = output_dir / "bgee_raw.jsonl"
        self._processed_output_path = output_dir / "bgee_processed.jsonl"

    def build_pipeline(self, client: ApiClient) -> ProcessorPipeline:  # noqa: ARG002
        return ProcessorPipeline(
            [
                ParserProcessor(parser=BgeeParser()),
                JSONLWriter(output_path=self._raw_output_path),
                OnedataConverter(metadata_builder=BgeeDataCiteBuilder()),  # type: ignore[type-arg]
                JSONLWriter(output_path=self._processed_output_path),
            ]
        )

    def create_client(self) -> BgeeClient:
        return BgeeClient(
            base_url=self.config.base_url,
            timeout=self.config.timeout,
            max_retries=self.config.max_retries,
        )

    def create_iterator(self, client: ApiClient) -> AsyncIterable[Any]:
        bgee_client = cast(BgeeClient, client)
        return bgee_client.iterate_datasets(
            BgeeIteratorOpts(
                start_url=self.config.base_url, max_records=self.config.max_records
            )
        )

    async def after_crawl(self) -> None:
        """Print first record's DataCite XML for conformity check."""
        if not (
            self._processed_output_path.exists()
            and self._processed_output_path.stat().st_size > 0
        ):
            return
        try:
            with open(self._processed_output_path, encoding="utf-8") as f:
                first_line = f.readline()
            record = json.loads(first_line)
            metadata_xml = record.get("metadata_xml", "")
            if metadata_xml:
                console.newline()
                console.section("First Record DataCite XML (Conformity Check)")
                dom = minidom.parseString(metadata_xml)
                pretty_xml = "\n".join(
                    line
                    for line in dom.toprettyxml(indent="  ").split("\n")
                    if line.strip() and not line.startswith("<?xml")
                )
                console.print(pretty_xml)
        except Exception as e:  # pylint: disable=broad-except
            console.debug(f"Could not print first record DataCite XML: {e}")

    def get_max_items(self) -> int | None:
        return self.config.max_records

    def _get_banner_subtitle(self) -> str | None:
        return f"Start URL: {self.config.base_url}"


class BgeeDataCiteBuilder(DataCiteBuilder):
    """DataCite builder customized for Bgee gene expression datasets."""

    creator_name = "Bgee"
    publisher_name = "Bgee"
    resource_type_general = "Dataset"
    resource_type_value = "Gene expression data"
    default_subjects = ["gene expression", "Bgee", "genomics", "transcriptomics"]
    default_rights = "CC0 1.0 Universal (CC0 1.0) Public Domain Dedication"

    def build_subjects_section(self, root: ET.Element, ctx: DataCiteContext) -> None:
        """Use per-dataset keywords, falling back to default subjects."""
        subjects = getattr(ctx.dataset, "keywords", None) or self.default_subjects
        if not subjects:
            return
        subjects_el = ET.SubElement(root, "subjects")
        for kw in subjects:
            ET.SubElement(subjects_el, "subject").text = kw

    def build_identifier_section(self, root: ET.Element, ctx: DataCiteContext) -> None:
        """Use URL identifier type since Bgee datasets have no DOI."""
        el = ET.SubElement(root, "identifier", {"identifierType": "URL"})
        el.text = ctx.dataset.identifier

    def build_related_identifiers_section(
        self, root: ET.Element, ctx: DataCiteContext
    ) -> None:
        """Add citation DOIs/URLs as related identifiers."""
        entries: list[tuple[str, str, str]] = []  # (identifier, type, relation)
        for citation in getattr(ctx.dataset, "citations", []):
            if "doi.org" in citation:
                entries.append((citation.split("doi.org/", 1)[-1], "DOI", "IsReferencedBy"))
            else:
                entries.append((citation, "URL", "IsReferencedBy"))
        if not entries:
            return
        related = ET.SubElement(root, "relatedIdentifiers")
        for identifier, id_type, relation in entries:
            el = ET.SubElement(
                related,
                "relatedIdentifier",
                {"relatedIdentifierType": id_type, "relationType": relation},
            )
            el.text = identifier

    def build_publication_year_section(self, root: ET.Element, ctx: DataCiteContext) -> None:
        """Use year from dataset datetime if available, fall back to current year."""
        year = ctx.publication_year
        if ctx.dataset.datetime:
            try:
                year = int(ctx.dataset.datetime[:4])
            except (ValueError, IndexError):
                pass
        ET.SubElement(root, "publicationYear").text = str(year)

    def build_dates_section(self, root: ET.Element, ctx: DataCiteContext) -> None:
        """Use `Updated` date type since the date comes from schema:dateModified/datePublished."""
        if not ctx.dataset.datetime:
            return
        dates = ET.SubElement(root, "dates")
        ET.SubElement(dates, "date", {"dateType": "Updated"}).text = ctx.dataset.datetime

    def build_descriptions_section(
        self, root: ET.Element, ctx: DataCiteContext
    ) -> None:
        """Use dataset-specific description if available, fall back to default."""
        desc = getattr(ctx.dataset, "description", None) or self.default_description
        if not desc:
            return
        descriptions = ET.SubElement(root, "descriptions")
        ET.SubElement(
            descriptions, "description", {"descriptionType": "Abstract"}
        ).text = desc
