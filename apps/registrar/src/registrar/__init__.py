"""
Dataset Registrar.

CLI for registering datasets from external open science services into a
single Onedata space — creates HTTP readonly storage and space support
on demand, registers files, creates public shares, and optionally mints
public-data-record identifiers (handles or share URLs).

Run via:

    python -m registrar register datasets.jsonl
    python -m registrar list-spaces
    python -m registrar list-storages
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

__version__ = "0.2.0"
