import os
import unittest
from unittest.mock import patch
from api import record_root


class RecordRootTests(unittest.TestCase):
    def test_configured_root(self):
        with patch.dict(os.environ, {"APP_DATA_DIR": "/tmp/records"}, clear=True):
            self.assertEqual(record_root(), "/tmp/records")
