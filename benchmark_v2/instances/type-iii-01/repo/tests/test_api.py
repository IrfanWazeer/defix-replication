import unittest
from api import invoice_amount


class InvoiceAmountTests(unittest.TestCase):
    def test_discount(self):
        self.assertEqual(invoice_amount(100, 15), 85)
