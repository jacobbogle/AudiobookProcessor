import pytest
from audiobook_p.main import parse_series_index_from_folder_name


@pytest.mark.parametrize("name,expected", [
    ("Vol. IX - The Old Ways", 9),
    ("Book IV", 4),
    ("Band 5 - German", 5),  # 'Band' is common in German; try to match digit
    ("Teil 07", 7),  # 'Teil' == part in German
    ("Livre 3", 3),  # French 'Livre' (book)
    ("Episode 12", 12),
    ("Disc 2", 2),
    ("Volume Ten", 10),  # written-out numbers now parsed for common words up to twenty
    ("Vol. 002", 2),
    ("[SPECIAL EDITION] Vol. 4", 4),
])
def test_tvsn_edgecases(name, expected):
    assert parse_series_index_from_folder_name(name) == expected


@pytest.mark.parametrize("name,expected", [
    ("Volume twenty-one", 21),
    ("Book one hundred", 100),
    ("Book two hundred thirty-four", 234),
    ("Vol. thirty", 30),
    ("Volume ninety-nine", 99),
])
def test_tvsn_compound_words(name, expected):
    assert parse_series_index_from_folder_name(name) == expected
