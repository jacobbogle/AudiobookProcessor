import unittest
import json
from audiobook_p.main import book_title_logic

class TestBookTitleLogicFromMetadata(unittest.TestCase):
    def test_title_and_title_sort(self):
        import os
        import pytest
        if not os.path.exists('test_metadata_output.json'):
            pytest.skip('test_metadata_output.json not present')
        with open('test_metadata_output.json') as f:
            data = json.load(f)
        if not data.get('title'):
            pytest.skip('test_metadata_output.json does not contain title')
        # Test the 'title' field
        actual_title = book_title_logic(data['title'])
        expected_title = "Master Imus's Transgression"
        print(f"book_title_logic(data['title']) = {actual_title!r}, expected = {expected_title!r}")
        self.assertEqual(actual_title, expected_title)
        # Test the 'title_sort' field
        actual_title_sort = book_title_logic(data['title_sort'])
        expected_title_sort = "Master Imus's Transgression"
        print(f"book_title_logic(data['title_sort']) = {actual_title_sort!r}, expected = {expected_title_sort!r}")
        self.assertEqual(actual_title_sort, expected_title_sort)

if __name__ == '__main__':
    unittest.main()
