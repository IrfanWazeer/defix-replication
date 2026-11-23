import unittest
from api import response_time


class ResponseTimeTests(unittest.TestCase):
    def test_response_time(self):
        self.assertEqual(response_time(), "2025-01-02T00:00:00+00:00")
