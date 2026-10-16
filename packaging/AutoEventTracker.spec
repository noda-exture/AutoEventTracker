# Build only explicit runtime resources; never collect the repository root.
from pathlib import Path
import sys

root = Path(SPECPATH).parent
stage = root / 'build' / 'installer-resources'
resources = [
    (str(root / name), '.') for name in
    ('global_config.json', 'styles.qss', 'record.js', 'recorder_events.js', 'recording_settings.js')
]
resources += [
    (str(root / 'assets' / 'autoeventtracker-icon-v2.png'), 'assets'),
    (str(root / 'node_modules'), 'node_modules'),
    (str(stage / 'defaults'), 'defaults'),
    (str(stage / 'licenses'), 'licenses'),
    (str(root / 'packaging' / 'THIRD_PARTY_NOTICES.txt'), '.'),
    (str(root / 'packaging' / 'recorder-smoke.cjs'), '.'),
    (str(root / 'packaging' / 'recorder-smoke-preload.cjs'), '.'),
]
a = Analysis(
    [str(root / 'bundle_entry.py')], pathex=[str(root)],
    binaries=[], datas=resources, hiddenimports=['tzdata'],
    excludes=['tkinter', 'matplotlib', 'numpy', 'pandas', 'IPython', 'pytest'],
    noarchive=False,
)
pyz = PYZ(a.pure)
icon = str(root / 'assets' / 'autoeventtracker-icon-v2.png')
gui = EXE(pyz, a.scripts, [], exclude_binaries=True, name='AutoEventTracker',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, icon=icon)
worker = EXE(pyz, a.scripts, [('u', None, 'OPTION')], exclude_binaries=True,
             name='AutoEventTrackerWorker', debug=False, strip=False, upx=False, console=True)
collection = COLLECT(gui, worker, a.binaries, a.datas, strip=False, upx=False, name='AutoEventTracker')
if sys.platform == 'darwin':
    app = BUNDLE(collection, name='AutoEventTracker.app', icon=icon,
                 bundle_identifier='com.exture.autoeventtracker',
                 info_plist={'CFBundleShortVersionString': '0.1.0',
                             'CFBundleVersion': '1',
                             'NSHighResolutionCapable': True,
                             'LSMinimumSystemVersion': '13.0'})
