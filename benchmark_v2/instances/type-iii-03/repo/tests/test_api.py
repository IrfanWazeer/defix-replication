import unittest
from api import run


class RunTests(unittest.TestCase):
    def test_default_attempt(self):
        calls = []

        def operation():
            calls.append(True)
            return True

        self.assertTrue(run(operation))
        self.assertEqual(len(calls), 1)
