import unittest
from api import has_email_shape


class EmailShapeTests(unittest.TestCase):
    def test_separator_order(self):
        self.assertFalse(has_email_shape("person.example@host"))
