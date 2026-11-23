import unittest
from pathlib import Path
from api import cache_file


class CacheFileTests(unittest.TestCase):
    def test_cache_file(self):
        self.assertEqual(cache_file("/var/cache", "entry.bin"), str(Path("/var/cache") / "entry.bin"))
