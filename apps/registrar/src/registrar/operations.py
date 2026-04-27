"""
Dataset Registration Operations

Pure functions implementing business logic for dataset registration.
Dependencies are passed explicitly as arguments.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2025 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from urllib.parse import urlparse

import requests

from registrar import output
from registrar.api import OnepanelClient, OneproviderClient, OnezoneClient
from registrar.cache import ResourceCache
from registrar.models import InputDataset, InputFile


def load_cache(
    onepanel: OnepanelClient,
    cache: ResourceCache,
) -> None:
    """
    Load all HTTP readonly spaces and storages into cache at startup.

    Only caches HTTP readonly storages with matching space names.

    Args:
        onepanel: Onepanel client
        cache: Resource cache to populate
    """
    output.info("Loading all spaces and storages into cache...")

    # Load all storages first
    storage_ids = onepanel.list_storages()
    output.debug(f"Found {len(storage_ids)} storages")

    for storage_id in storage_ids:
        details = onepanel.get_storage_details(storage_id)
        storage_name = details.get("name")
        storage_type = details.get("type")
        is_readonly = details.get("readonly", False)

        # Only cache HTTP readonly storages
        if storage_type == "http" and is_readonly and storage_name:
            cache.add_storage(name=storage_name, storage_id=storage_id, details=details)
            output.debug(f"Cached HTTP readonly storage: {storage_name} ({storage_id})")

    output.info(f"Cached {len(cache.storages)} HTTP readonly storages")

    # Load all spaces
    space_ids = onepanel.list_spaces()
    output.debug(f"Found {len(space_ids)} spaces")

    for space_id in space_ids:
        details = onepanel.get_space_details(space_id)
        space_name: str | None = details.get("name")
        space_storage_id: str | None = details.get("storageId")

        if not space_name or not space_storage_id:
            continue

        # Check if this space is supported by a cached HTTP readonly storage
        storage_in_cache = cache.get_storage_by_name(space_name)

        if storage_in_cache and storage_in_cache["id"] == space_storage_id:
            cache.add_space(
                name=space_name,
                space_id=space_id,
                storage_id=space_storage_id,
                details=details,
            )
            output.debug(f"Cached space: {space_name} ({space_id}) with storage {space_storage_id}")

    output.info(f"Cached {len(cache.spaces)} spaces with HTTP readonly storages")


def ensure_space_and_storage(
    onepanel: OnepanelClient,
    onezone: OnezoneClient,
    cache: ResourceCache,
    domain: str,
    default_size: int = 1099511627776,
) -> tuple[str, str, str]:
    """
    Ensure that a space and HTTP storage exist for the given domain.
    Creates them if they don't exist in cache.

    Args:
        onepanel: Onepanel client
        onezone: Onezone client
        cache: Resource cache
        domain: Domain name (will be used as space and storage name)
        default_size: Default space support size in bytes

    Returns:
        Tuple of (space_id, space_name, storage_id)
    """
    output.debug(f"Ensuring space and storage for domain: {domain}")

    # Check cache
    cached_space = cache.get_space_by_name(domain)
    if cached_space:
        output.debug(f"Found space '{domain}' in cache")
        return cached_space["id"], domain, cached_space["storage_id"]

    # Space doesn't exist in cache, create it
    output.info(f"Creating new space and storage for domain: {domain}")

    # Create storage first
    storage_id = onepanel.add_storage(name=domain, endpoint=f"https://{domain}")
    storage_details = onepanel.get_storage_details(storage_id)
    cache.add_storage(name=domain, storage_id=storage_id, details=storage_details)

    # Create space
    space_id = onezone.create_space(name=domain)

    # Create support token
    support_token = onezone.create_support_token(space_id)

    # Support the space with storage
    onepanel.support_space(storage_id=storage_id, support_token=support_token, size=default_size)

    # Get space details and add to cache
    space_details = onepanel.get_space_details(space_id)
    cache.add_space(
        name=domain,
        space_id=space_id,
        storage_id=storage_id,
        details=space_details,
    )

    output.info(f"Created space '{domain}' (ID: {space_id}) with storage {storage_id}")

    return space_id, domain, storage_id


def register_dataset_files(  # noqa: PLR0913
    oneprovider: OneproviderClient,
    space_name: str,
    space_id: str,
    storage_id: str,
    location: str,
    files: list[InputFile],
) -> tuple[int, int]:
    """
    Register all files for a dataset.

    Args:
        oneprovider: Oneprovider client
        space_name: Space name
        space_id: Space ID
        storage_id: Storage ID
        location: Dataset location (directory path in space)
        files: List of files to register

    Returns:
        Tuple of (registered_count, skipped_count)
    """
    registered = 0
    skipped = 0

    for file_info in files:
        file_path = file_info.path.strip("/") if file_info.path else ""
        file_url = file_info.url

        if not file_url:
            output.warning(f"File '{file_path}' has no URL, skipping")
            continue

        # Build destination path
        dest_path = f"{location}/{file_path}"

        # Check if file already exists
        file_id = oneprovider.lookup_file_id(space_name=space_name, path=dest_path)

        if file_id:
            output.debug(f"File already exists: {dest_path}")
            skipped += 1
        else:
            # Register the file
            output.debug(f"Registering file: {dest_path}")
            try:
                oneprovider.register_file(
                    storage_id=storage_id,
                    space_id=space_id,
                    file_url=file_url,
                    dest_path=dest_path,
                )
                registered += 1
            except requests.RequestException as e:
                output.error(f"Failed to register file {dest_path}: {e}")
                continue

    return registered, skipped


def find_or_create_share(
    oneprovider: OneproviderClient,
    file_id: str,
    name: str,
    description: str = "",
) -> str:
    """
    Find existing share or create a new one for a file/directory.

    Checks if a share with the expected name and description already exists.

    Args:
        oneprovider: Oneprovider client
        file_id: File or directory ID
        name: Share name
        description: Share description

    Returns:
        Share ID (existing or newly created)
    """
    # Get file attributes to check for existing shares
    file_attrs = oneprovider.get_file_attrs(file_id)

    if file_attrs and "shares" in file_attrs:
        # Check each existing share
        for share_id in file_attrs["shares"]:
            share_details = oneprovider.get_share_details(share_id)

            if share_details:
                existing_name = share_details.get("name", "")
                existing_desc = share_details.get("description", "")

                # Check if share matches our requirements
                if existing_name == name and existing_desc == description:
                    output.debug(f"Share already exists: '{name}' with ID: {share_id}")
                    return share_id

    # Share doesn't exist, create it
    return oneprovider.create_share(file_id=file_id, name=name, description=description)


def find_or_register_handle(
    onezone: OnezoneClient,
    oneprovider: OneproviderClient,
    handle_service_id: str,
    share_id: str,
    metadata_xml: str,
) -> str | None:
    """
    Find existing handle or register a new one for a share.

    Checks if the share already has a handle registered.

    Args:
        onezone: Onezone client
        oneprovider: Oneprovider client
        handle_service_id: Handle service ID
        share_id: Share ID
        metadata_xml: Metadata in DataCite/OpenAIRE XML format

    Returns:
        Handle ID (existing or newly registered), or None if not configured
    """
    if not handle_service_id:
        output.debug("Handle service not configured, skipping handle registration")
        return None

    # Get share details to check for existing handle
    share_details = oneprovider.get_share_details(share_id)

    if share_details and share_details.get("handleId"):
        handle_id = share_details["handleId"]
        output.debug(f"Share already has handle: {handle_id}")
        return handle_id

    # Handle doesn't exist, register it
    return onezone.register_handle(
        handle_service_id=handle_service_id,
        share_id=share_id,
        metadata_xml=metadata_xml,
    )


def extract_domain_from_dataset(dataset: InputDataset) -> str | None:
    """
    Extract domain from dataset's first file URL.

    Args:
        dataset: Input dataset

    Returns:
        Domain string or None if not found
    """
    if not dataset.files:
        return None

    first_file_url = dataset.files[0].url
    if not first_file_url:
        return None

    parsed_url = urlparse(first_file_url)
    return parsed_url.netloc or None
