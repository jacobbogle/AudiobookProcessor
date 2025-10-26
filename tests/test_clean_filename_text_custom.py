import pytest
from audiobook_p.utils import clean_filename_text

def test_clean_filename_text_custom_cases():
    cases = [
        ("01 01 sea of souls", "01 Sea of Souls"),
        ("titan's curse", "Titan's Curse"),
        ("Half-blood", "Half-blood"),
    ]
    for input_val, expected in cases:
        result = clean_filename_text(input_val)
        print(f"clean_filename_text({input_val!r}) => {result!r}")
        assert result == expected
