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
