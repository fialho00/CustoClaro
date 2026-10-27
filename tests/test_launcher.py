import unittest
from launcher import normalize_key

class LauncherKeyTests(unittest.TestCase):
    def test_key_formats_without_strict_prefix(self):
        self.assertEqual(normalize_key('GEMINI_API_KEY="AIza_EXAMPLE"'), 'AIza_EXAMPLE')
        self.assertEqual(normalize_key('another_key_format'), 'another_key_format')
        with self.assertRaises(ValueError):
            normalize_key('one\nOTHER=bad')
