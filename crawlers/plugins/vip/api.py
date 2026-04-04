"""
VIP API Client.

Girder REST API client for VIP (Virtual Imaging Platform).
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import dataclass
from typing import AsyncIterator, assert_never

from crawlers.core.api import ApiClient, ApiFailure
from crawlers.core.result import Err, Ok, Result
from crawlers.ui import console


@dataclass
class VipFile:
    """A downloadable file within a VIP dataset folder."""

    name: str
    """Relative path from the dataset root (e.g. 'subdir/file.txt')."""
    url: str
    """Direct download URL via Girder item download endpoint."""


@dataclass
class VipIteratorOpts:
    """Options for VIP dataset iteration."""

    collection: str
    """Name of the collection to crawl."""
    page_size: int = 100
    max_records: int | None = None


class VipClient(ApiClient[VipIteratorOpts, dict]):
    """
    Girder REST API client for the VIP platform.

    Resolves a named collection to its ID, paginates the top-level
    dataset folders, and recursively collects all nested files for
    each dataset before yielding.
    """

    async def list_collections(self) -> Result[list[dict], ApiFailure]:
        """
        Fetch all available collections.

        Returns:
            Ok(list[dict]) where each dict is a Girder collection object,
            or Err(ApiFailure) on HTTP/network error.
        """
        url = f"{self.base_url}/collection?limit=250&offset=0&sort=name&sortdir=1"
        result = await self.get_json(url)
        if isinstance(result, Err):
            return result
        return Ok(_to_list(result.value))

    # pylint: disable=invalid-overridden-method
    async def iterate_datasets(self, opts: VipIteratorOpts) -> AsyncIterator[dict]:
        """
        Iterate over top-level dataset folders in the named collection.

        Resolves the collection name to its Girder ID, then pages through
        root-level folders. For each folder, all nested files are collected
        recursively before yielding.

        Yields:
            dict with keys:
              - 'folder': raw Girder folder JSON
              - 'files': list[VipFile] (all files, paths relative to folder root)
        """
        collection_id = await self._resolve_collection_id(opts.collection)
        if not collection_id:
            console.error(f"Collection not found: {opts.collection!r}")
            return

        total = await self._get_collection_folder_count(collection_id)
        console.info(f"Found {total} datasets in collection {opts.collection!r}")

        yielded = 0
        offset = 0

        while offset < total:
            folders = await self._list_folders(
                parent_type="collection",
                parent_id=collection_id,
                limit=opts.page_size,
                offset=offset,
            )
            if not folders:
                break

            for folder in folders:
                if opts.max_records is not None and yielded >= opts.max_records:
                    console.info(f"Reached max_records limit: {opts.max_records}")
                    return

                folder_id = folder.get("_id", "")
                folder_name = folder.get("name", folder_id)

                console.info(f"📁 Collecting files for dataset: {folder_name}")
                files = await self._collect_files(
                    folder_id=folder_id,
                    path_prefix="",
                    page_size=opts.page_size,
                )
                yield {"folder": folder, "files": files}
                yielded += 1
                console.info(
                    f"✅ [{yielded}/{total}] {folder_name} — {len(files)} file(s)"
                )

            offset += len(folders)

    async def _resolve_collection_id(self, name: str) -> str | None:
        """Look up collection ID by name."""
        result = await self.list_collections()
        match result:
            case Ok(value=collections):
                for coll in collections:
                    if coll.get("name") == name:
                        return coll.get("_id")
                available = [c.get("name", "?") for c in collections]
                console.error(
                    f"Collection {name!r} not found. "
                    f"Available: {', '.join(available)}"
                )
                return None
            case Err(value=err):
                console.error(f"Failed to list collections: {err}")
                return None
            case other:
                assert_never(other)

    async def _get_collection_folder_count(self, collection_id: str) -> int:
        """Return the number of top-level folders in a collection."""
        url = f"{self.base_url}/collection/{collection_id}/details"
        match await self.get_json(url):
            case Ok(value=data):
                return data.get("nFolders", 0)
            case Err(value=err):
                console.warning(f"Failed to get collection details: {err}")
                return 0
            case other:
                assert_never(other)

    async def _list_folders(
        self,
        parent_type: str,
        parent_id: str,
        limit: int,
        offset: int,
    ) -> list[dict]:
        """Fetch one page of child folders."""
        url = (
            f"{self.base_url}/folder"
            f"?limit={limit}&offset={offset}&sort=name&sortdir=1"
            f"&parentType={parent_type}&parentId={parent_id}"
        )
        match await self.get_json(url):
            case Ok(value=data):
                return _to_list(data)
            case Err(value=err):
                console.warning(
                    f"Failed to list folders ({parent_type}/{parent_id}): {err}"
                )
                return []
            case other:
                assert_never(other)

    async def _collect_files(
        self,
        folder_id: str,
        path_prefix: str,
        page_size: int,
    ) -> list[VipFile]:
        """
        Recursively collect all downloadable files under a folder.

        Args:
            folder_id: Girder folder ID to start from.
            path_prefix: Path built up by parent calls (empty for the dataset root).
            page_size: Page size for API pagination.

        Returns:
            Flat list of VipFile with relative paths from the dataset root.
        """
        files: list[VipFile] = []
        n_folders, n_items = await self._get_folder_details(folder_id)

        if n_items > 0:
            offset = 0
            while True:
                items = await self._list_items(folder_id, page_size, offset)
                if not items:
                    break
                for item in items:
                    item_id = item.get("_id", "")
                    item_name = item.get("name", item_id)
                    file_path = (
                        f"{path_prefix}/{item_name}" if path_prefix else item_name
                    )
                    files.append(
                        VipFile(
                            name=file_path,
                            url=f"{self.base_url}/item/{item_id}/download",
                        )
                    )
                offset += len(items)
                if offset >= n_items:
                    break

        if n_folders > 0:
            offset = 0
            while True:
                subfolders = await self._list_folders(
                    "folder", folder_id, page_size, offset
                )
                if not subfolders:
                    break
                for subfolder in subfolders:
                    sub_id = subfolder.get("_id", "")
                    sub_name = subfolder.get("name", sub_id)
                    sub_prefix = (
                        f"{path_prefix}/{sub_name}" if path_prefix else sub_name
                    )
                    sub_files = await self._collect_files(sub_id, sub_prefix, page_size)
                    files.extend(sub_files)
                offset += len(subfolders)
                if offset >= n_folders:
                    break

        return files

    async def _get_folder_details(self, folder_id: str) -> tuple[int, int]:
        """Return (nFolders, nItems) for a folder."""
        url = f"{self.base_url}/folder/{folder_id}/details"
        match await self.get_json(url):
            case Ok(value=data):
                return data.get("nFolders", 0), data.get("nItems", 0)
            case Err(value=err):
                console.warning(f"Failed to get folder details for {folder_id}: {err}")
                return 0, 0
            case other:
                assert_never(other)

    async def _list_items(
        self,
        folder_id: str,
        limit: int,
        offset: int,
    ) -> list[dict]:
        """Fetch one page of items (files) inside a folder."""
        url = (
            f"{self.base_url}/item"
            f"?limit={limit}&offset={offset}&sort=name&sortdir=1"
            f"&folderId={folder_id}"
        )
        match await self.get_json(url):
            case Ok(value=data):
                return _to_list(data)
            case Err(value=err):
                console.warning(f"Failed to list items for folder {folder_id}: {err}")
                return []
            case other:
                assert_never(other)


def _to_list(data: list | dict) -> list[dict]:
    """
    Normalise a Girder paginated response to a plain list.

    Older Girder versions return a dict with numeric string keys
    (``{"0": {...}, "1": {...}}``); newer versions return a plain JSON array.
    """
    if isinstance(data, list):
        return data
    return list(data.values())
