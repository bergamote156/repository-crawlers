"""
Dataset Registrar entry point.

Usage:
    python -m registrar <command> [options]

Example:
    python -m registrar register datasets.json
    python -m registrar list-spaces
    python -m registrar show-config
"""

from registrar.cli import main

if __name__ == "__main__":
    main()
