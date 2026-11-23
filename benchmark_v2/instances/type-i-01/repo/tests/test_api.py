import unittest
from api import distance


class DistanceTests(unittest.TestCase):
    def test_distance(self):
        self.assertEqual(distance(3, 4), 5)
