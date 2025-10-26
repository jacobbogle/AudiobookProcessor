import pytest
from audiobook_p.utils import clean_filename_text

def test_clean_filename_text_basic():
    # Basic cases
    cases = [
        ("01 - File Name.mp3", "File Name.mp3"),
        ("file name", "File Name"),
        ("THE FILE NAME", "The File Name"),
        ("file<>name", "Filename"),
        ("file|name", "Filename"),
        ('file"name', "Filename"),
        ("file?name", "Filename"),
        ("file*name", "Filename"),
        ("", ""),
        (None, None),
        ("???", ""),
        ("file_name", "File Name"),
        ("file   name.mp3", "File Name.mp3"),
        ("01 - 2020 report.pdf", "2020 Report.pdf"),
        ("123_file.TXT", "123 File.TXT"),
    ]
    for input_val, expected in cases:
        result = clean_filename_text(input_val)
        print(f"clean_filename_text({input_val!r}) => {result!r}")
        assert result == expected
