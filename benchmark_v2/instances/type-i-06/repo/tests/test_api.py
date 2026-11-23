import unittest
from api import mean_value


class MeanValueTests(unittest.TestCase):
    def test_mean_value(self):
        self.assertEqual(mean_value([2, 4, 6]), 4)
