import io
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch, MagicMock

from global_settings import (GLOBAL_CONFIG_PATH, load_global_config, resolve_device,
                             device_context_options, load_recording_viewport, validate_recording_viewport)
from main import ScenarioWorker, AutoRecordWorker
from tracker import run_tracker


class GlobalSettingsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'global_config.json'
        self.config = json.loads(GLOBAL_CONFIG_PATH.read_text())

    def save(self):
        self.path.write_text(json.dumps(self.config), encoding='utf-8')

    def test_default_and_explicit_devices(self):
        self.config['default_device'] = 'android_phone'
        self.save()
        self.assertEqual(resolve_device(path=self.path)['id'], 'android_phone')
        self.assertEqual(resolve_device('desktop', self.path)['id'], 'desktop')
        options = device_context_options(resolve_device(path=self.path))
        self.assertTrue(options['is_mobile'])
        self.assertEqual(options['screen'], {'width': 390, 'height': 844})
        self.assertNotIn('name', options)
        self.assertNotIn('id', options)

    def test_configuration_edits_are_reloaded(self):
        self.save()
        original = resolve_device('desktop', self.path)
        self.config['devices']['desktop']['viewport']['width'] = 1440
        self.save()
        self.assertEqual(resolve_device('desktop', self.path)['viewport']['width'], 1440)
        self.assertEqual(original['viewport']['width'], 1280)

    def test_null_user_agent_uses_browser_default(self):
        self.config['devices']['desktop']['user_agent'] = None
        self.save()
        self.assertNotIn('user_agent', device_context_options(resolve_device(path=self.path)))

    def test_invalid_profiles_fail_instead_of_silent_fallback(self):
        original = deepcopy(self.config)
        for key, value in [('viewport', {'width': 0, 'height': 800}),
                           ('screen', {'width': True, 'height': 800}),
                           ('device_scale_factor', float('nan')),
                           ('is_mobile', 'false'), ('user_agent', ''), ('name', '')]:
            with self.subTest(key=key):
                self.config = deepcopy(original)
                self.config['devices']['desktop'][key] = value
                self.save()
                with self.assertRaises(ValueError):
                    load_global_config(self.path)
        self.config = original
        self.save()
        with self.assertRaises(ValueError):
            resolve_device('missing', self.path)
        self.config['default_device'] = 'missing'
        self.save()
        with self.assertRaises(ValueError):
            load_global_config(self.path)

    def test_missing_or_malformed_file(self):
        with self.assertRaises(ValueError):
            load_global_config(self.path)
        self.path.write_text('{invalid')
        with self.assertRaises(ValueError):
            load_global_config(self.path)

    def test_worker_passes_device_to_cli(self):
        process = MagicMock()
        process.stdout = io.StringIO('')
        process.wait.return_value = 0
        with patch('main.subprocess.Popen', return_value=process) as popen:
            ScenarioWorker('sample', 'scenario.json', True, device='android_phone').run()
        command = popen.call_args[0][0]
        self.assertEqual(command[command.index('--device') + 1], 'android_phone')
        self.assertIn('--headless', command)

    def test_unknown_device_stops_before_browser_launch(self):
        with patch('tracker.sync_playwright') as playwright:
            self.assertFalse(run_tracker('sample', 'scenario.json', device='missing'))
        playwright.assert_not_called()

    def test_recording_viewport_and_worker_override(self):
        self.config['recording'] = {'viewport': {'width': 1440, 'height': 900}}
        self.save()
        self.assertEqual(load_recording_viewport(self.path), {'width': 1440, 'height': 900})
        process = MagicMock()
        process.stdout = io.StringIO('')
        process.wait.return_value = 0
        with patch('main.subprocess.Popen', return_value=process) as popen:
            AutoRecordWorker('sample', 'test.json', 'https://example.test', '',
                             viewport={'width': 1024, 'height': 768}).run()
        self.assertEqual(popen.call_args[0][0][-2:], ['1024', '768'])

    def test_invalid_recording_sizes(self):
        for size in (None, {}, {'width': True, 'height': 800},
                     {'width': 0, 'height': 800}, {'width': 1280, 'height': 16385}):
            with self.subTest(size=size), self.assertRaises(ValueError):
                validate_recording_viewport(size)
