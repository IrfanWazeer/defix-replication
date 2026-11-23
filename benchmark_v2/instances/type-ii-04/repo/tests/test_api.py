import unittest
from datetime import date
from api import days_booked


class BookingDaysTests(unittest.TestCase):
    def test_single_day(self):
        self.assertEqual(days_booked(date(2025, 5, 1), date(2025, 5, 1)), 1)
