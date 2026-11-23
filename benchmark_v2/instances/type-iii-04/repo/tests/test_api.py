import unittest
from api import create_account


class AccountTests(unittest.TestCase):
    def test_account_fields(self):
        self.assertEqual(create_account("u-4", "a@example.test"), {"id": "u-4", "email": "a@example.test"})
