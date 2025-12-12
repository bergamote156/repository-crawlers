"""
Dataset Registrar

A tool for registering datasets from external open science services into Onedata.
It automatically creates HTTP storages and spaces as needed, registers files,
creates public shares, and optionally registers DOI handles.

Architecture Overview
---------------------
The registrar is organized into several modules with clear responsibilities:

- **api/**: Onedata REST API clients (Onepanel, Onezone, Oneprovider)
- **models.py**: Data structures (InputDataset, RegistrationResult)
- **cache.py**: ResourceCache for spaces/storages
- **operations.py**: Business logic functions
- **registrar.py**: High-level orchestration (DatasetRegistrar)
- **cli.py**: Command-line interface

See docs/ARCHITECTURE.md for detailed documentation.

Quick Start
-----------
    # Register datasets from JSON file
    python -m registrar register datasets.json

    # List HTTP readonly spaces
    python -m registrar list-spaces

    # Show current configuration
    python -m registrar show-config
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2025 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

__version__ = "0.1.0"
