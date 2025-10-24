import pytest

from audiobook_p import main


def test_author_last_first_simple():
    assert main._author_last_first_to_first_last("Smith, John") == "John Smith"


def test_author_last_first_middle():
    assert main._author_last_first_to_first_last("Doe, Jane A.") == "Jane A. Doe"


def test_maybe_fix_author_flag_false():
    assert main._maybe_fix_author("Smith, John", False) == "Smith, John"


def test_maybe_fix_author_none():
    assert main._maybe_fix_author(None, True) is None
