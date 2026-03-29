"""Tests for structured error types and to_json serialization."""

# pylint: disable=missing-function-docstring

from dataclasses import FrozenInstanceError

from crawlers.core import errors
from crawlers.core.errors import HttpError, HttpTimeoutError


class TestHttpError:
    """Tests for HttpError dataclass."""

    def test_to_json_contains_type(self):
        err = HttpError(status=404, method="GET", url="https://example.com/data")
        d = err.to_json()
        assert d["type"] == "http_error"

    def test_to_json_contains_fields(self):
        err = HttpError(status=403, method="HEAD", url="https://example.com/x")
        d = err.to_json()
        assert d["status"] == 403
        assert d["method"] == "HEAD"
        assert d["url"] == "https://example.com/x"

    def test_to_json_empty_body_by_default(self):
        err = HttpError(status=500, method="GET", url="https://example.com/")
        assert err.to_json()["body"] == ""

    def test_to_json_with_body(self):
        err = HttpError(
            status=400, method="GET", url="https://example.com/", body="Bad Request"
        )
        assert err.to_json()["body"] == "Bad Request"

    def test_str_representation(self):
        err = HttpError(status=404, method="GET", url="https://example.com/missing")
        assert "404" in str(err)
        assert "GET" in str(err)
        assert "https://example.com/missing" in str(err)

    def test_is_frozen(self):
        err = HttpError(status=200, method="GET", url="https://example.com/")
        try:
            err.status = 500  # type: ignore[misc]
        except FrozenInstanceError:
            return
        raise AssertionError("Should have raised FrozenInstanceError")


class TestHttpTimeoutError:
    """Tests for HttpTimeoutError dataclass."""

    def test_to_json_contains_type(self):
        err = HttpTimeoutError(
            method="GET",
            url="https://example.com/slow",
            attempts=3,
            last_error="Connection reset",
        )
        assert err.to_json()["type"] == "timeout_error"

    def test_to_json_contains_fields(self):
        err = HttpTimeoutError(
            method="GET",
            url="https://example.com/slow",
            attempts=5,
            last_error="Timeout",
        )
        d = err.to_json()
        assert d["method"] == "GET"
        assert d["url"] == "https://example.com/slow"
        assert d["attempts"] == 5
        assert d["last_error"] == "Timeout"

    def test_str_representation(self):
        err = HttpTimeoutError(
            method="GET",
            url="https://example.com/slow",
            attempts=3,
            last_error="Timeout",
        )
        s = str(err)
        assert "3" in s
        assert "https://example.com/slow" in s


class TestToJson:
    """Tests for errors.to_json() serialization helper."""

    def test_dict_returned_as_is(self):
        d = {"reason": "test", "id": "abc"}
        assert errors.to_json(d) is d

    def test_object_with_to_json_called(self):
        err = HttpError(status=404, method="GET", url="https://example.com/")
        result = errors.to_json(err)
        assert result["type"] == "http_error"
        assert result["status"] == 404

    def test_unknown_object_wrapped_in_dict(self):
        result = errors.to_json("something went wrong")
        assert result == {"error": "something went wrong"}

    def test_exception_wrapped_in_dict(self):
        exc = ValueError("bad value")
        result = errors.to_json(exc)
        assert "error" in result
        assert "bad value" in result["error"]
