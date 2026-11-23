import os
import unittest
from unittest.mock import patch
from api import listener_port


class ListenerPortTests(unittest.TestCase):
    def test_default_port(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(listener_port(), 8080)
