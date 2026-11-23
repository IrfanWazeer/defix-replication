import os
import tempfile
import unittest
from api import message


class MessageTests(unittest.TestCase):
    def test_message_from_other_working_directory(self):
        previous = os.getcwd()
        with tempfile.TemporaryDirectory() as other_directory:
            try:
                os.chdir(other_directory)
                self.assertEqual(message(), "service ready")
            finally:
                os.chdir(previous)
