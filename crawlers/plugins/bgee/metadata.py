"""Bgee DataCite Metadata Builder."""

__author__ = "Vincent Emonet"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import xml.etree.ElementTree as ET

from crawlers.core.metadata.datacite import DataCiteBuilder, DataCiteContext


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

    def build_related_identifiers_section(self, root: ET.Element, ctx: DataCiteContext) -> None:
        """Add self_link + citation DOIs as related identifiers."""
        entries: list[tuple[str, str, str]] = []  # (identifier, type, relation)
        if ctx.dataset.self_link:
            entries.append((ctx.dataset.self_link, "URL", "IsSupplementTo"))
        for citation in getattr(ctx.dataset, "citations", []):
            id_type = "DOI" if "doi.org" in citation else "URL"
            entries.append((citation, id_type, "IsReferencedBy"))
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

    def build_descriptions_section(self, root: ET.Element, ctx: DataCiteContext) -> None:
        """Use dataset-specific description if available, fall back to default."""
        desc = getattr(ctx.dataset, "description", None) or self.default_description
        if not desc:
            return
        descriptions = ET.SubElement(root, "descriptions")
        description = ET.SubElement(
            descriptions, "description", {"descriptionType": "Abstract"}
        )
        description.text = desc
