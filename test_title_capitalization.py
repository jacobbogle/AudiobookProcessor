import unittest
from audiobook_p.main import book_title_logic

class TestBookTitleLogic(unittest.TestCase):
    def test_capitalization(self):
        # Should always capitalize first letter
        self.assertEqual(book_title_logic('chapter one'), 'Chapter one')
        self.assertEqual(book_title_logic('01 chapter one'), 'Chapter one')
        self.assertEqual(book_title_logic('1 introduction'), 'Introduction')
        self.assertEqual(book_title_logic('01 01 the beginning'), '01 The beginning')
        self.assertEqual(book_title_logic('Already Capitalized'), 'Already Capitalized')
        self.assertEqual(book_title_logic(''), '')
        self.assertEqual(book_title_logic(None), None)

if __name__ == '__main__':
    unittest.main()
