"""
Dataset Registrar

High-level orchestration for dataset registration in Onedata.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2025 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import json
from pathlib import Path
from typing import Optional

import requests

from registrar import operations, output
from registrar.api import OnepanelClient, OneproviderClient, OnezoneClient
from registrar.cache import ResourceCache
from registrar.config import Config
from registrar.models import InputDataset, RegistrationResult, RegistrationSummary

# Output formatting constants
_SEPARATOR = "=" * 70


class DatasetRegistrar:  # pylint: disable=too-few-public-methods
    """
    High-level orchestrator for dataset registration.

    Coordinates API clients, cache, and operations to register datasets
    from external sources into Onedata.
    """

    def __init__(self, config: Config):
        """
        Initialize the registrar with configuration.

        Args:
            config: Configuration object
        """
        self.config = config
        self.cache = ResourceCache()

        # Initialize API clients
        self.onepanel = OnepanelClient(
            domain=config.onedata.oneprovider_domain,
            token=config.tokens.admin_token,
            port=config.onedata.panel_port,
            verify_ssl=config.onedata.verify_ssl,
        )
        self.onezone = OnezoneClient(
            domain=config.onedata.onezone_domain,
            token=config.tokens.space_owner_token,
            verify_ssl=config.onedata.verify_ssl,
        )
        self.oneprovider = OneproviderClient(
            domain=config.onedata.oneprovider_domain,
            token=config.tokens.space_owner_token,
            verify_ssl=config.onedata.verify_ssl,
        )

    def run(
        self,
        datasets_file: Path,
        limit: Optional[int] = None,
        dry_run: bool = False,
    ) -> RegistrationSummary:
        """
        Run registration for all datasets in file.

        Args:
            datasets_file: Path to JSON (.json) or JSONL (.jsonl) file with datasets
            limit: Maximum number of datasets to process (None = all)
            dry_run: If True, validate without registering

        Returns:
            RegistrationSummary with results
        """
        output.always(_SEPARATOR)
        output.always("Dataset Registration Started")
        output.always(_SEPARATOR)

        output.info(f"Onezone: {self.config.onedata.onezone_domain}")
        output.info(f"Oneprovider: {self.config.onedata.oneprovider_domain}")

        if dry_run:
            output.warning("DRY RUN MODE - no changes will be made")

        # Load cache
        if not dry_run:
            try:
                operations.load_cache(onepanel=self.onepanel, cache=self.cache)
            except requests.RequestException as e:
                output.error(f"Failed to load cache: {e}")
                raise

        # Load datasets
        try:
            datasets = self._load_datasets(datasets_file, limit)
        except FileNotFoundError:
            output.error(f"Datasets file not found: {datasets_file}")
            raise
        except json.JSONDecodeError as e:
            output.error(f"Failed to parse datasets file: {e}")
            raise
        except ValueError as e:
            output.error(str(e))
            raise

        output.info(f"Loaded {len(datasets)} datasets from {datasets_file}")

        # Process each dataset
        summary = RegistrationSummary()

        for idx, dataset in enumerate(datasets, 1):
            output.info(f"\n[{idx}/{len(datasets)}] Processing: {dataset.name}")

            if dry_run:
                result = self._validate_dataset(dataset)
            else:
                result = self._process_dataset(dataset)

            summary.handle_result(result)

            if result.success:
                output.info(
                    f"  OK: {result.files_registered} registered, "
                    f"{result.files_skipped} skipped"
                )
            else:
                output.error(f"  FAILED: {result.error}")

        # Summary
        output.always("")
        output.always(_SEPARATOR)
        output.stats(
            f"Complete: {summary.successful} successful, {summary.failed} failed"
        )
        output.stats(
            f"Files: {summary.total_files_registered} registered, "
            f"{summary.total_files_skipped} skipped"
        )
        output.always(_SEPARATOR)

        return summary

    def _load_datasets(
        self, datasets_file: Path, limit: Optional[int]
    ) -> list[InputDataset]:
        """
        Load datasets from JSON or JSONL file.

        File format is determined by extension:
        - .json: Standard JSON (array or single object)
        - .jsonl: JSON Lines (one JSON object per line)

        Args:
            datasets_file: Path to JSON/JSONL file with datasets
            limit: Maximum number of datasets to load (None = all)

        Returns:
            List of InputDataset objects

        Raises:
            ValueError: If file format is not supported
            json.JSONDecodeError: If JSON parsing fails
        """
        suffix = datasets_file.suffix.lower()

        if suffix == ".jsonl":
            datasets = self._load_datasets_jsonl(datasets_file, limit)
        elif suffix == ".json":
            datasets = self._load_datasets_json(datasets_file, limit)
        else:
            raise ValueError(f"Unsupported file format: {suffix}. Use .json or .jsonl")

        return datasets

    def _load_datasets_json(
        self, datasets_file: Path, limit: Optional[int]
    ) -> list[InputDataset]:
        """Load datasets from standard JSON file."""
        with open(datasets_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Handle both array and single object
        if isinstance(data, dict):
            data = [data]

        datasets = [InputDataset.from_dict(d) for d in data]

        if limit is not None:
            datasets = datasets[:limit]

        return datasets

    def _load_datasets_jsonl(
        self, datasets_file: Path, limit: Optional[int]
    ) -> list[InputDataset]:
        """
        Load datasets from JSONL file (one JSON object per line).

        This format is memory-efficient for large files as it processes
        line by line and stops early if limit is reached.
        """
        datasets: list[InputDataset] = []

        with open(datasets_file, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:  # Skip empty lines
                    continue

                try:
                    data = json.loads(line)
                    datasets.append(InputDataset.from_dict(data))
                except json.JSONDecodeError as e:
                    raise json.JSONDecodeError(
                        f"Line {line_no}: {e.msg}", e.doc, e.pos
                    ) from e

                if limit is not None and len(datasets) >= limit:
                    break

        return datasets

    @staticmethod
    def _validate_dataset_basics(
        dataset: InputDataset,
    ) -> tuple[Optional[RegistrationResult], Optional[str]]:
        """
        Validate basic dataset requirements.

        Args:
            dataset: Dataset to validate

        Returns:
            Tuple of (error_result, domain):
            - If validation fails: (RegistrationResult with error, None)
            - If validation passes: (None, extracted_domain)
        """
        # Check for required fields
        if not dataset.name:
            return (
                RegistrationResult(
                    dataset_name="Unknown",
                    success=False,
                    error="Missing dataset name",
                ),
                None,
            )

        if not dataset.files:
            return (
                RegistrationResult(
                    dataset_name=dataset.name,
                    success=False,
                    error="No files in dataset",
                ),
                None,
            )

        # Extract domain
        domain = operations.extract_domain_from_dataset(dataset)
        if not domain:
            return (
                RegistrationResult(
                    dataset_name=dataset.name,
                    success=False,
                    error="Could not extract domain from file URLs",
                ),
                None,
            )

        return None, domain

    def _validate_dataset(self, dataset: InputDataset) -> RegistrationResult:
        """Validate dataset without registering (dry run)."""
        error_result, domain = self._validate_dataset_basics(dataset)
        if error_result:
            return error_result

        assert domain is not None  # Guaranteed by _validate_dataset_basics
        output.debug(f"  Domain: {domain}")
        output.debug(f"  Files: {len(dataset.files)}")
        output.debug(f"  Location: {dataset.location}")

        return RegistrationResult(
            dataset_name=dataset.name,
            success=True,
            files_registered=0,
            files_skipped=len(dataset.files),
        )

    def _process_dataset(self, dataset: InputDataset) -> RegistrationResult:
        """Process a single dataset: register files, create share."""
        try:
            # Validate basic requirements
            error_result, domain = self._validate_dataset_basics(dataset)
            if error_result:
                return error_result

            assert domain is not None  # Guaranteed by _validate_dataset_basics
            output.debug(f"  Domain: {domain}")

            # Ensure space and storage exist
            space_id, space_name, storage_id = operations.ensure_space_and_storage(
                onepanel=self.onepanel,
                onezone=self.onezone,
                cache=self.cache,
                domain=domain,
                default_size=self.config.storage.default_size,
            )

            # Register files
            location = dataset.location.strip("/")
            registered, skipped = operations.register_dataset_files(
                oneprovider=self.oneprovider,
                space_name=space_name,
                space_id=space_id,
                storage_id=storage_id,
                location=location,
                files=dataset.files,
            )

            # Create share
            share_id = None
            dir_file_id = self.oneprovider.lookup_file_id(
                space_name=space_name, path=location
            )
            if dir_file_id:
                share_id = operations.find_or_create_share(
                    oneprovider=self.oneprovider,
                    file_id=dir_file_id,
                    name=dataset.name,
                    description=dataset.pid,
                )

            # Register handle (if configured)
            if share_id and dataset.metadata_xml:
                operations.find_or_register_handle(
                    onezone=self.onezone,
                    oneprovider=self.oneprovider,
                    handle_service_id=self.config.tokens.handle_service_id,
                    share_id=share_id,
                    metadata_xml=dataset.metadata_xml,
                )

            return RegistrationResult(
                dataset_name=dataset.name,
                success=True,
                files_registered=registered,
                files_skipped=skipped,
            )

        except requests.RequestException as e:
            return RegistrationResult(
                dataset_name=dataset.name,
                success=False,
                error=str(e),
            )
