import unittest
from api import setting_value


class SettingValueTests(unittest.TestCase):
    def test_setting_value(self):
        self.assertEqual(setting_value(), "enabled=true")
