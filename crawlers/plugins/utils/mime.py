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
