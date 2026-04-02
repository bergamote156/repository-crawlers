"""Bgee Crawler and DataCite metadata builder."""

__author__ = "Vincent Emonet"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import xml.etree.ElementTree as ET

from crawlers.metadata.datacite import DataCiteBuilder, DataCiteContext


class BgeeDataCiteBuilder(DataCiteBuilder):
    """DataCite XML builder customized for Bgee gene expression datasets."""

    creator_name = "Bgee"
    publisher_name = "Bgee"
    resource_type_general = "Dataset"
    resource_type_value = "Gene expression data"
    default_subjects = ["gene expression", "Bgee", "genomics", "transcriptomics"]
    default_rights = "CC0 1.0 Universal (CC0 1.0) Public Domain Dedication"

    def get_sections(self):  # type: ignore[override]
        """Add version section to the standard pipeline."""
        return [*super().get_sections(), self.build_version_section]

    def build_creators_section(self, root: ET.Element, ctx: DataCiteContext) -> None:
        """Use creator name and URL from the dataset, falling back to class defaults."""
        name = getattr(ctx.dataset, "creator_name", None) or self.creator_name
        url = getattr(ctx.dataset, "creator_url", None)
        creators = ET.SubElement(root, "creators")
        creator = ET.SubElement(creators, "creator")
        ET.SubElement(creator, "creatorName", {"nameType": "Organizational"}).text = (
            name
        )
        if url:
            ET.SubElement(
                creator, "nameIdentifier", {"nameIdentifierScheme": "URL"}
            ).text = url

    def build_version_section(self, root: ET.Element, ctx: DataCiteContext) -> None:
        """Emit dataset version if available."""
        version = getattr(ctx.dataset, "version", None)
        if version:
            ET.SubElement(root, "version").text = version

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
                entries.append(
                    (citation.split("doi.org/", 1)[-1], "DOI", "IsReferencedBy")
                )
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

    def build_publication_year_section(
        self, root: ET.Element, ctx: DataCiteContext
    ) -> None:
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
        ET.SubElement(dates, "date", {"dateType": "Updated"}).text = (
            ctx.dataset.datetime
        )

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
