import pytest
from audiobook_p.main import parse_series_index_from_folder_name


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
    assert parse_series_index_from_folder_name(name) == expected
