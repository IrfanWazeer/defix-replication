import unittest
from api import order_shipping


class ShippingTests(unittest.TestCase):
    def test_express_shipping(self):
        self.assertEqual(order_shipping(1, True), 15)
