"""
Dataset Registrar

A tool for registering datasets from external open science services into Onedata.
It automatically creates HTTP storages and spaces as needed, registers files,
creates public shares, and optionally registers DOI handles.

Quick Start
-----------
    # Register datasets from JSON file
    python -m registrar register datasets.json

    # List HTTP readonly spaces
    python -m registrar list-spaces

    # Show current configuration
    python -m registrar show-config

See docs/ARCHITECTURE.md for detailed architecture documentation.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2025 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

__version__ = "0.1.0"
