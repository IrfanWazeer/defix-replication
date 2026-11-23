import unittest
from datetime import date
from api import display_date


class DisplayDateTests(unittest.TestCase):
    def test_custom_pattern(self):
        self.assertEqual(display_date(date(2025, 7, 9), "%Y/%m/%d"), "2025/07/09")
