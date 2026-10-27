"""Key configuration must remain local and take precedence over stale shell state."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import launcher
import vision


class LauncherKeyTests(unittest.TestCase):
    def test_key_round_trip_and_stale_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.env').write_text('OTHER=keep\nGEMINI_API_KEY=old\n')
            with patch.object(launcher, 'ROOT', root), patch.object(vision, '__file__', str(root / 'vision.py')):
                with patch.dict(os.environ, {'GEMINI_API_KEY': 'stale-key'}):
                    launcher.save_key('GEMINI_API_KEY="AIza_TEST_KEY"')
                    self.assertEqual(vision.configured_api_key(), 'AIza_TEST_KEY')
            self.assertEqual((root / '.env').read_text(), 'OTHER=keep\nGEMINI_API_KEY=AIza_TEST_KEY\n')

    def test_multiline_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(launcher, 'ROOT', Path(directory)):
            with self.assertRaises(ValueError):
                launcher.save_key('AIza_TEST\nOTHER=bad')
            self.assertFalse((Path(directory) / '.env').exists())
