import unittest
from api import timeout


class TimeoutTests(unittest.TestCase):
    def test_timeout(self):
        self.assertEqual(timeout({"timeout": 12}), 12)
