import unittest
from api import record_label


class RecordLabelTests(unittest.TestCase):
    def test_record_label(self):
        self.assertEqual(record_label("Report", "Lee"), "Report (Lee)")
