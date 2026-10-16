import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import runtime_paths


class RuntimePathsTests(unittest.TestCase):
    def test_first_launch_creates_only_defaults_and_preserves_user_changes(self):
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            bundle = base / 'bundle'
            user = base / 'user data'
            (bundle / 'defaults').mkdir(parents=True)
            (bundle / 'global_config.json').write_text('{"default":true}')
            (bundle / 'defaults' / 'template.xlsx').write_bytes(b'generic-template')
            (bundle / 'project' / 'private-client').mkdir(parents=True)
            with patch.dict(os.environ, {'AET_DATA_DIR': str(user)}), \
                 patch('runtime_paths.is_bundled', return_value=True), \
                 patch('runtime_paths.resource_path', side_effect=lambda *parts: bundle.joinpath(*parts)):
                try:
                    runtime_paths.initialize_runtime()
                    self.assertEqual(Path.cwd(), user.resolve())
                    self.assertEqual(list((user / 'project').iterdir()), [user / 'project' / 'template.xlsx'])
                    (user / 'global_config.json').write_text('custom-settings')
                    (user / 'project' / 'template.xlsx').write_bytes(b'custom-template')
                    runtime_paths.initialize_runtime()
                    self.assertEqual((user / 'global_config.json').read_text(), 'custom-settings')
                    self.assertEqual((user / 'project' / 'template.xlsx').read_bytes(), b'custom-template')
                    self.assertEqual(os.environ['PLAYWRIGHT_BROWSERS_PATH'], str(bundle / 'browsers'))
                finally:
                    os.chdir(previous)

    def test_bundled_commands_do_not_require_python_or_node_on_path(self):
        with patch('runtime_paths.is_bundled', return_value=True), \
             patch('runtime_paths.sys.executable', '/apps/AutoEventTracker'), \
             patch('runtime_paths.sys.platform', 'darwin'), \
             patch('runtime_paths.resource_path', side_effect=lambda *parts: Path('/resources').joinpath(*parts)):
            self.assertEqual(runtime_paths.tracker_command(), [str(Path('/apps/AutoEventTrackerWorker')), '--run-tracker'])
            self.assertEqual(runtime_paths.recorder_command(), [str(Path('/resources/playwright/driver/node')), str(Path('/resources/record.js'))])

    def test_windows_commands_use_executable_suffix(self):
        with patch('runtime_paths.is_bundled', return_value=True), \
             patch('runtime_paths.sys.executable', '/apps/AutoEventTracker.exe'), \
             patch('runtime_paths.sys.platform', 'win32'):
            self.assertTrue(runtime_paths.tracker_command()[0].endswith('AutoEventTrackerWorker.exe'))
            self.assertTrue(runtime_paths.recorder_command()[0].endswith('node.exe'))
