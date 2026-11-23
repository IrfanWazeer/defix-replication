import unittest
from api import page


class PageTests(unittest.TestCase):
    def test_second_page(self):
        self.assertEqual(page(list(range(6)), 2, 3), [3, 4, 5])
