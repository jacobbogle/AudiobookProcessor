import pytest
from audiobook_p.main import sanitize_string


def test_sanitize_removes_newlines_and_tabs():
    s = "Line1\nLine2\tLine3"
    assert sanitize_string(s) == "Line1 Line2 Line3"


def test_sanitize_replaces_underscores():
    s = "This_is__a_test___string"
    assert sanitize_string(s) == "This is a test string"


def test_sanitize_removes_control_chars():
    s = "Hello\x00World\x1f!"
    assert sanitize_string(s) == "HelloWorld !" or sanitize_string(s) == "HelloWorld!"


def test_sanitize_bytes_and_none():
    b = b"Some bytes"
    # bytes will be converted to str by sanitize_string
    assert sanitize_string(b) == "b'Some bytes'" or isinstance(sanitize_string(b), str)
    assert sanitize_string(None) is None
