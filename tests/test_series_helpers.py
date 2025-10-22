import pytest
from audiobook_p.main import parse_series_index_from_folder_name

@pytest.mark.parametrize('name,expected', [
    ('Book 03', 3),
    ('Vol. 2', 2),
    ('Volume 10', 10),
    ('#4', 4),
    ('01 - The Beginning', 1),
    ('1 The Start', 1),
    ('1-book title', 1),
    ('01. Title', 1),
    ('(01) Title', 1),
    ('01.Title', 1),
    ('Book 2 of 12', 2),
    ('Some Title', None),
    ('Series 007', 7),
    ('Part 5', 5),
    ('My Book 12', 12),
    ('NoNumberHere', None)
])
def test_parse_series_index(name, expected):
    assert parse_series_index_from_folder_name(name) == expected
