import unittest
from pathlib import PurePath
from api import output_name


class OutputNameTests(unittest.TestCase):
    def test_output_name(self):
        self.assertEqual(output_name("reports/item.txt"), str(PurePath("reports/item.txt")))
