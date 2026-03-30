"""
EODC DataCite Metadata Builder.

Specialized DataCite builder for EODC Sentinel-1 data.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from crawlers.metadata.datacite import DataCiteBuilder


## TODO defaults suited only for sentinel-1 gdr collection - not adequate for others?
## Maybe make those as fields in models?
class EODCDataCiteBuilder(DataCiteBuilder):
    """
    DataCite builder specialized for EODC Sentinel-1 data.

    Configures default values specific to Copernicus/ESA data.
    """

    # Creator: European Space Agency
    creator_name = "European Space Agency"

    # Publisher: EODC
    publisher_name = "EODC"

    # Resource type
    resource_type_general = "Dataset"
    resource_type_value = "Earth observation data"

    # Default subjects for Sentinel-1 data
    default_subjects = [
        "Sentinel-1",
        "Synthetic Aperture Radar",
        "SAR",
        "GRD",
        "Copernicus",
    ]

    # Description for Sentinel-1 GRD products
    default_description = (
        "Sentinel-1 Level-1 Ground Range Detected (GRD) product "
        "acquired in Interferometric Wide (IW) mode. "
        "Data provided as part of the Copernicus Earth Observation programme."
    )

    # Copernicus open access licence
    default_rights = "Copernicus Open Access Licence"
