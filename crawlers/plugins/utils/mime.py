"""MIME type inference from file extensions."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"


# Ordered: longer suffixes first so ".tar.gz" wins over ".gz".
_MIME_TYPES: tuple[tuple[str, str], ...] = (
    (".tar.gz", "application/gzip"),
    (".tgz", "application/gzip"),
    (".tar", "application/x-tar"),
    (".gz", "application/gzip"),
    (".zip", "application/zip"),
    (".pdf", "application/pdf"),
    (".csv", "text/csv"),
    (".json", "application/json"),
    (".geojson", "application/geo+json"),
    (".xml", "application/xml"),
    (".nc", "application/x-netcdf"),
    (".hdf5", "application/x-hdf5"),
    (".hdf", "application/x-hdf"),
    (".h5", "application/x-hdf5"),
    (".txt", "text/plain"),
    (".png", "image/png"),
    (".jpg", "image/jpeg"),
    (".jpeg", "image/jpeg"),
    (".tif", "image/tiff"),
    (".tiff", "image/tiff"),
)


def infer_mime_type(url: str) -> str | None:
    """Return a MIME type guessed from a URL's file extension, or None."""
    url_lower = url.lower()
    for ext, mime in _MIME_TYPES:
        if url_lower.endswith(ext):
            return mime
    return None


# Canonical extension to emit for a given MIME type. Hand-picked because
# multiple suffixes can map to the same MIME (e.g. .tar.gz / .gz → gzip).
_MIME_TO_EXT: dict[str, str] = {
    "application/gzip": "gz",
    "application/x-tar": "tar",
    "application/zip": "zip",
    "application/pdf": "pdf",
    "text/csv": "csv",
    "application/json": "json",
    "application/geo+json": "geojson",
    "application/xml": "xml",
    "application/x-netcdf": "nc",
    "application/x-hdf5": "h5",
    "application/x-hdf": "hdf",
    "text/plain": "txt",
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/tiff": "tiff",
}


def extension_for_mime(mime: str | None) -> str | None:
    """Return a canonical file extension (without dot) for a MIME type, or None.

    Strips MIME parameters ('image/tiff; profile=cloud-optimized' → 'tiff').
    """
    if not mime:
        return None

    base = mime.split(";", 1)[0].strip().lower()
    return _MIME_TO_EXT.get(base)
