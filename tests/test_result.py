"""Tests for Ok and Err result types."""

# pylint: disable=missing-function-docstring

import pytest

from crawlers.core.result import Err, Ok


class TestOk:
    """Tests for the Ok variant."""

    def test_is_ok(self):
        assert Ok(42).is_ok() is True

    def test_is_err(self):
        assert Ok(42).is_err() is False

    def test_unwrap_returns_value(self):
        assert Ok("hello").unwrap() == "hello"

    def test_unwrap_or_returns_value(self):
        assert Ok(42).unwrap_or(0) == 42

    def test_err_raises(self):
        with pytest.raises(ValueError):
            Ok(42).err()

    def test_map_transforms_value(self):
        result = Ok(3).map(lambda x: x * 2)
        assert result == Ok(6)

    def test_map_returns_ok(self):
        assert isinstance(Ok(1).map(str), Ok)

    def test_equality(self):
        assert Ok(42) == Ok(42)
        assert Ok(42) != Ok(0)

    def test_inequality_with_err(self):
        assert Ok(42) != Err(42)

    def test_repr(self):
        assert repr(Ok(42)) == "Ok(42)"

    def test_none_value(self):
        result = Ok(None)
        assert result.is_ok()
        assert result.unwrap() is None

    def test_pattern_matching_ok(self):
        result = Ok(99)
        matched = False
        match result:
            case Ok(value=v):
                assert v == 99
                matched = True
        assert matched

    def test_pattern_matching_misses_err(self):
        result = Err("oops")
        matched = False
        match result:
            case Ok():
                matched = True
        assert not matched


class TestErr:
    """Tests for the Err variant."""

    def test_is_ok(self):
        assert Err("fail").is_ok() is False

    def test_is_err(self):
        assert Err("fail").is_err() is True

    def test_unwrap_raises(self):
        with pytest.raises(ValueError):
            Err("fail").unwrap()

    def test_unwrap_or_returns_default(self):
        assert Err("fail").unwrap_or(99) == 99

    def test_err_returns_value(self):
        assert Err("reason").err() == "reason"

    def test_map_passes_through(self):
        err = Err("reason")
        result = err.map(lambda x: x * 2)
        assert result == err

    def test_map_returns_err(self):
        assert isinstance(Err("x").map(str), Err)

    def test_equality(self):
        assert Err("x") == Err("x")
        assert Err("x") != Err("y")

    def test_inequality_with_ok(self):
        assert Err(42) != Ok(42)

    def test_repr(self):
        assert repr(Err("oops")) == "Err('oops')"

    def test_dict_error(self):
        err = Err({"reason": "not_found", "id": "abc"})
        assert err.is_err()
        assert err.err()["reason"] == "not_found"

    def test_pattern_matching_err(self):
        result = Err("boom")
        matched = False
        match result:
            case Err(value=v):
                assert v == "boom"
                matched = True
        assert matched

    def test_pattern_matching_misses_ok(self):
        result = Ok(1)
        matched = False
        match result:
            case Err():
                matched = True
        assert not matched
