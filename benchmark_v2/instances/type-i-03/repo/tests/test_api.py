import unittest
from api import request_value


class RequestValueTests(unittest.TestCase):
    def test_request_value(self):
        self.assertEqual(request_value('{"value": 7}'), 7)
