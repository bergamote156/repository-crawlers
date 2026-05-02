"""
Tests for custom argparse Action classes.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import argparse

import pytest

from confline.ui.actions import CountAction, HeterogeneousTupleAction


def test_heterogeneous_tuple_action_dispatches_per_position():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--coords",
        nargs=2,
        action=HeterogeneousTupleAction,
        types=(int, str),
    )
    ns = parser.parse_args(["--coords", "5", "north"])
    assert ns.coords == (5, "north")


def test_heterogeneous_tuple_wrong_length_errors():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--coords",
        nargs=1,
        action=HeterogeneousTupleAction,
        types=(int, str),  # mismatched
    )
    with pytest.raises(SystemExit):
        parser.parse_args(["--coords", "5"])


def test_heterogeneous_tuple_invalid_value_errors():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pair",
        nargs=2,
        action=HeterogeneousTupleAction,
        types=(int, int),
    )
    with pytest.raises(SystemExit):
        parser.parse_args(["--pair", "abc", "5"])


def test_count_action_starts_from_zero():
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", action=CountAction, default=argparse.SUPPRESS)
    ns = parser.parse_args(["-v", "-v"])
    assert ns.v == 2


def test_count_action_under_suppress_omits_when_unused():
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", action=CountAction, default=argparse.SUPPRESS)
    ns = parser.parse_args([])
    assert "v" not in vars(ns)
