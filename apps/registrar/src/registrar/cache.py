"""
Resource Cache

Cache for spaces and storages to minimize API calls.
Only tracks HTTP readonly storages with matching space names.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2025 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"


class ResourceCache:
    """
    Cache for spaces and storages to minimize API calls.

    Only HTTP readonly storages with matching space names are cached.
    This is the convention used for dataset registration where:
    - Storage name = domain (e.g., "example.com")
    - Space name = domain (same as storage)

    Usage:
        cache = ResourceCache()
        cache.add_space(name="example", space_id="abc123", storage_id="def456")
        cached = cache.get_space_by_name("example")
    """

    def __init__(self):
        # name -> {id, details, storage_id}
        self.spaces: dict[str, dict] = {}
        # name -> {id, details}
        self.storages: dict[str, dict] = {}

    def get_space_by_name(self, name: str) -> dict | None:
        """Get space from cache by name."""
        return self.spaces.get(name)

    def add_space(
        self,
        name: str,
        space_id: str,
        storage_id: str,
        details: dict | None = None,
    ) -> None:
        """Add space to cache."""
        self.spaces[name] = {
            "id": space_id,
            "storage_id": storage_id,
            "details": details or {},
        }

    def get_storage_by_name(self, name: str) -> dict | None:
        """Get storage from cache by name."""
        return self.storages.get(name)

    def add_storage(
        self,
        name: str,
        storage_id: str,
        details: dict | None = None,
    ) -> None:
        """Add storage to cache."""
        self.storages[name] = {
            "id": storage_id,
            "details": details or {},
        }

    def clear(self) -> None:
        """Clear all cached data."""
        self.spaces.clear()
        self.storages.clear()

    def __repr__(self) -> str:
        return f"ResourceCache(spaces={len(self.spaces)}, storages={len(self.storages)})"
