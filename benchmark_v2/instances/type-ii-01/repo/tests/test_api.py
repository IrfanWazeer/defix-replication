import unittest
from api import within_range


class RangeTests(unittest.TestCase):
    def test_upper_endpoint(self):
        self.assertTrue(within_range(10, 2, 10))
