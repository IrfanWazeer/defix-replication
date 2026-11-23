import unittest
from api import value_for


class LookupTests(unittest.TestCase):
    def test_value_for(self):
        self.assertEqual(value_for("code", {"code": "ready"}), "READY")
