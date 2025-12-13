"""
eCUDO Crawler

A modular crawler for discovering and processing public scientific datasets
from eCUDO.pl for registration in Onedata.

Quick Start
-----------
    # List organizations
    python -m ecudo list-orgs

    # Crawl an organization
    python -m ecudo crawl iopan --max-records 100

    # Convert output
    python -m ecudo convert data/iopan_processed.jsonl

See docs/ARCHITECTURE.md for detailed architecture documentation.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2025 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

__version__ = "0.3.0"
