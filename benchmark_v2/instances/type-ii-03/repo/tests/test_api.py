import unittest
from api import manage_access


class ManagementAccessTests(unittest.TestCase):
    def test_administrator_access(self):
        self.assertTrue(manage_access("admin"))
