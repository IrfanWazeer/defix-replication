import unittest
from api import seconds


class SecondsTests(unittest.TestCase):
    def test_configured_duration(self):
        self.assertEqual(seconds({"duration": {"milliseconds": 2500}}), 2.5)
