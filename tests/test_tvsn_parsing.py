import pytest
from audiobook_p.main import parse_series_index_from_folder_name
try:
    from tests.legacy_test_converter import legacy_test_converter
except ImportError:
    legacy_test_converter = None

@pytest.mark.parametrize("name,expected", [
    ("Vol.1 - The Beginning", 1),
    ("volume-2: The Next", 2),
    ("{Vol - 3} Special Edition", 3),
    ("[Vol.4] Collector's", 4),
    ("(5) Short Title", 5),
    ("<6> Another", 6),
    ("Book 07", 7),
    ("01 - Prelude", 1),
    ("03.Title", 3),
    ("#8", 8),
    ("9 of 12", 9),
    ("Some Name 10", 10),
    ("NoNumberHere", None),
])
def test_tvsn_parsing(name, expected):
    try:
        assert parse_series_index_from_folder_name(name) == expected
    except Exception as e:
        if legacy_test_converter:
            result = legacy_test_converter({'name': name, 'expected': expected})
            assert result.get('expected') == expected
        else:
            raise
