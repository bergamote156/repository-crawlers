"""
VIP DataCite Metadata Builder.

DataCite XML builder for VIP (Virtual Imaging Platform) datasets.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import xml.etree.ElementTree as ET

from crawlers.metadata.datacite import DataCiteBuilder, DataCiteContext


class VipDataCiteBuilder(DataCiteBuilder):
    """
    DataCite XML builder for VIP (Virtual Imaging Platform) datasets.

    VIP is a web platform for medical image simulation and processing
    hosted by CREATIS lab (INSA Lyon). Datasets are typically MRI/neuroimaging
    acquisitions stored in Girder collections.
    """

    creator_name = "CREATIS"
    publisher_name = "VIP (Virtual Imaging Platform)"
    resource_type_general = "Dataset"
    resource_type_value = "Medical imaging data"
    default_subjects = [
        "medical imaging",
        "MRI",
        "in-vivo imaging",
        "VIP",
        "CREATIS",
    ]
    default_rights = "Contact data owner for usage terms"

    def build_identifier_section(self, root: ET.Element, ctx: DataCiteContext) -> None:
        """Use URL identifier since VIP datasets have no DOI."""
        el = ET.SubElement(root, "identifier", {"identifierType": "Other"})
        el.text = ctx.dataset.identifier

    def build_creators_section(self, root: ET.Element, ctx: DataCiteContext) -> None:
        """Use OWNER from folder meta when available, fall back to class default."""
        meta = getattr(ctx.dataset, "meta", {})
        name = meta.get("OWNER") or self.creator_name

        creators = ET.SubElement(root, "creators")
        creator = ET.SubElement(creators, "creator")
        ET.SubElement(creator, "creatorName", {"nameType": "Personal"}).text = name

    def build_subjects_section(self, root: ET.Element, ctx: DataCiteContext) -> None:
        """
        Combine default subjects with dataset-specific terms from folder meta:
        SUBJECT_study_modalities (e.g. 'MR_Modality'), SUBJECT_type (e.g. 'Quadruped'),
        ORIGIN (e.g. 'Bruker BioSpin MRI GmbH').
        """
        meta = getattr(ctx.dataset, "meta", {})

        extra: list[str] = []
        for field_name in ("SUBJECT_study_modalities", "SUBJECT_type", "ORIGIN"):
            value = meta.get(field_name)
            if value and value not in self.default_subjects and value not in extra:
                extra.append(value)

        subjects = self.default_subjects + extra
        if not subjects:
            return

        subjects_el = ET.SubElement(root, "subjects")
        for kw in subjects:
            ET.SubElement(subjects_el, "subject").text = kw

    def build_publication_year_section(
        self, root: ET.Element, ctx: DataCiteContext
    ) -> None:
        """Derive year from dataset datetime when available."""
        year = ctx.publication_year
        if ctx.dataset.datetime:
            try:
                year = int(ctx.dataset.datetime[:4])
            except (ValueError, IndexError):
                pass
        ET.SubElement(root, "publicationYear").text = str(year)

    def build_dates_section(self, root: ET.Element, ctx: DataCiteContext) -> None:
        """Emit the folder updated/created timestamp as an 'Updated' date."""
        if not ctx.dataset.datetime:
            return
        dates = ET.SubElement(root, "dates")
        ET.SubElement(dates, "date", {"dateType": "Updated"}).text = (
            ctx.dataset.datetime
        )

    def build_descriptions_section(
        self, root: ET.Element, ctx: DataCiteContext
    ) -> None:
        """Use per-dataset description (from meta.TITLE or folder description)."""
        desc = getattr(ctx.dataset, "description", None) or self.default_description
        if not desc:
            return
        descriptions = ET.SubElement(root, "descriptions")
        ET.SubElement(
            descriptions, "description", {"descriptionType": "Abstract"}
        ).text = desc
