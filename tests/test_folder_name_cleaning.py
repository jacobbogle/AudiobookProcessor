import pytest
from audiobook_p.utils import clean_folder_name, clean_filename_text, sanitize_string, book_title_logic



class TestFolderNameCleaning:
    def test_sanitize_string_function(self):
        # Basic whitespace normalization
        assert sanitize_string("  foo   bar  ") == "foo bar"
        # Tabs and newlines
        assert sanitize_string("foo\tbar\nqux") == "foo bar qux"
        # Control characters
        assert sanitize_string("foo\x00bar\x1fqux") == "foobar qux"
        # Underscores replaced by default
        assert sanitize_string("foo_bar_baz") == "foo bar baz"
        # Underscores not replaced if specified
        assert sanitize_string("foo_bar_baz", replace_underscores=False) == "foo_bar_baz"
        # Leading/trailing whitespace
        assert sanitize_string("   foo bar   ") == "foo bar"
        # None input
        assert sanitize_string(None) is None
        # Numeric input
        assert sanitize_string(123) == "123"
    def test_clean_folder_name_apostrophe_and_hyphen(self):
        assert clean_folder_name("titan's cure") == "Titan's Cure"
        assert clean_folder_name("half-blood") == "Half-blood"
        assert clean_folder_name("the-old-dog") == "The Old Dog"
        assert clean_folder_name("Old-dog") == "Old-dog"
    """Test suite for folder name cleaning and sanitizing functions."""

    def test_clean_folder_name_basic(self):
        assert clean_folder_name("01 - Album Name") == "Album Name"
        assert clean_folder_name("01. Album Name") == "Album Name"
        assert clean_folder_name("1: Album Name") == "Album Name"
        assert clean_folder_name("(01) Album Name") == "Album Name"

    def test_clean_folder_name_no_numbers(self):
        assert clean_folder_name("Album Name") == "Album Name"
        assert clean_folder_name("The Album Name") == "The Album Name"

    def test_clean_folder_name_title_case(self):
        assert clean_folder_name("album name") == "Album Name"
        assert clean_folder_name("THE ALBUM NAME") == "The Album Name"

    def test_clean_folder_name_edge_cases(self):
        assert clean_folder_name("") == ""
        assert clean_folder_name(None) is None
        assert clean_folder_name("   ") == ""
        assert clean_folder_name("123") == "123"  # All digits, should remain

    def test_clean_folder_name_special_chars(self):
        assert clean_folder_name("01_album_name") == "Album Name"
        assert clean_folder_name("01-album-name") == "Album Name"
        assert clean_folder_name("01 - book.mp3") == "Book Mp3"
        assert clean_folder_name("01a - book") == "Book"

    def test_clean_folder_name_series_basic(self):
        assert clean_folder_name("01 - Series Name") == "Series Name"
        assert clean_folder_name("series_name") == "Series Name"
        assert clean_folder_name("series-name") == "Series Name"

    def test_clean_folder_name_series_title_case(self):
        assert clean_folder_name("series name") == "Series Name"
        assert clean_folder_name("THE SERIES NAME") == "The Series Name"

    def test_clean_folder_name_series_leading_punctuation(self):
        assert clean_folder_name("---Series Name") == "Series Name"
        assert clean_folder_name("...Series Name") == "Series Name"
        assert clean_folder_name("___Series Name") == "Series Name"

    def test_clean_folder_name_series_multiple_spaces(self):
        assert clean_folder_name("Series    Name") == "Series Name"
        assert clean_folder_name("Series__Name") == "Series Name"
        assert clean_folder_name("Series--Name") == "Series Name"

    def test_clean_folder_name_series_edge_cases(self):
        assert clean_folder_name("") == ""
        assert clean_folder_name(None) is None
        assert clean_folder_name("   ") == ""
        assert clean_folder_name("123") == "123"

    def test_clean_folder_name_series_complex(self):
        assert clean_folder_name("01_The-Great.Series") == "The Great Series"
        assert clean_folder_name("  02 - the great series  ") == "The Great Series"

    def test_sanitize_string_basic(self):
        """Test basic string sanitization."""
        assert sanitize_string("  hello   world  ") == "hello world"
        assert sanitize_string("hello\tworld") == "hello world"
        assert sanitize_string("hello\x00world") == "helloworld"  # Control chars removed

    def test_sanitize_string_underscores(self):
        """Test underscore replacement."""
        assert sanitize_string("hello_world", replace_underscores=True) == "hello world"
        assert sanitize_string("hello_world", replace_underscores=False) == "hello_world"

    def test_sanitize_string_edge_cases(self):
        """Test edge cases for sanitize_string."""
        assert sanitize_string("") == ""
        assert sanitize_string(None) is None
        assert sanitize_string(123) == "123"

    def test_book_title_logic_basic(self):
        """Test basic book title logic."""
        assert book_title_logic("01 - Book Title") == "Book Title"
        assert book_title_logic("Book Title") == "Book Title"

    def test_book_title_logic_capitalization(self):
        """Test capitalization in book title logic."""
        assert book_title_logic("book title") == "Book title"
        assert book_title_logic("the book title") == "The book title"
        assert book_title_logic("123 book title") == "Book title"

    def test_book_title_logic_edge_cases(self):
        """Test edge cases for book_title_logic."""
        assert book_title_logic("") == ""
        assert book_title_logic(None) is None
        assert book_title_logic("123") == "123"

    def test_integration_clean_folder_name(self):
        test_cases = [
            ("01 - The Album", "The Album"),
            ("02. Another Album", "Another Album"),
            ("album name", "Album Name"),
            ("THE ALBUM", "The Album"),
            ("01_album_name", "Album Name"),
            ("01 - book.mp3", "Book Mp3"),
            ("01a - book", "Book"),
        ]
        for input_name, expected in test_cases:
            assert clean_folder_name(input_name) == expected

    def test_integration_clean_folder_name_series(self):
        test_cases = [
            ("01 - The Series", "The Series"),
            ("the_series_name", "The Series Name"),
            ("THE-SERIES", "The Series"),
            ("  02 - the great series  ", "The Great Series"),
            ("01_The.Great.Series", "The Great Series"),
        ]
        for input_name, expected in test_cases:
            assert clean_folder_name(input_name) == expected

    def test_clean_filename_text_basic(self):
        """Test basic filename text cleaning."""
        assert clean_filename_text("01 - File Name.mp3") == "File Name.mp3"
        assert clean_filename_text("file name") == "File Name"
        assert clean_filename_text("THE FILE NAME") == "The File Name"

    def test_clean_filename_text_filesystem_safe(self):
        """Test that clean_filename_text removes filesystem-problematic characters."""
        assert clean_filename_text("file<>name") == "Filename"
        assert clean_filename_text("file|name") == "Filename"
        assert clean_filename_text('file"name') == "Filename"
        assert clean_filename_text("file?name") == "Filename"
        assert clean_filename_text("file*name") == "Filename"

    def test_clean_filename_text_edge_cases(self):
        """Test edge cases for clean_filename_text."""
        assert clean_filename_text("") == ""
        assert clean_filename_text(None) is None
        assert clean_filename_text("???") == ""  # All invalid chars become empty

    def test_title_case_book_like_titles(self):
        # These should be properly title-cased, with small words lowercased unless first/last
        cases = [
            ("wind in the sails", "Wind in the Sails"),
            ("trapped in a hole", "Trapped in a Hole"),
            ("turn to the right", "Turn to the Right"),
            ("a turn to the right", "A Turn to the Right"),
            ("the wind in the sails", "The Wind in the Sails"),
            ("wind In The Sails", "Wind in the Sails"),
            ("Trapped In A Hole", "Trapped in a Hole"),
            ("Turn To The Right", "Turn to the Right"),
        ]
        for input_val, expected in cases:
            assert clean_folder_name(input_val) == expected
            assert clean_filename_text(input_val) == expected