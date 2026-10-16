"""Build a native, self-contained installer on macOS or Windows."""
import argparse
import hashlib
from importlib.metadata import distributions
import json
import os
from pathlib import Path
import platform
import plistlib
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = '0.1.0'


def run(command, **kwargs):
    print('+', ' '.join(map(str, command)), flush=True)
    return subprocess.run(list(map(str, command)), check=True, **kwargs)


def assert_no_project(root):
    forbidden = [path for path in root.rglob('*') if path.name in ('project', '.DS_Store', '.git')]
    if forbidden:
        raise RuntimeError(f'Forbidden data in distribution: {forbidden[:10]}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser-cache', type=Path, help='Optional existing Playwright download cache')
    parser.add_argument('--skip-build', action='store_true', help='Recheck/package an existing local build')
    args = parser.parse_args()
    os.chdir(ROOT)
    stage = ROOT / 'build' / 'installer-resources'
    browsers = stage / 'browsers'
    defaults = stage / 'defaults'
    installers = ROOT / 'installers'
    for folder in (browsers, defaults, installers):
        folder.mkdir(parents=True, exist_ok=True)
    if not args.skip_build:
        sys.path.insert(0, str(ROOT))
        from create_template import create_comprehensive_template
        create_comprehensive_template(str(defaults / 'template.xlsx'))
        licenses = stage / 'licenses'
        shutil.copytree(ROOT / 'packaging' / 'licenses', licenses, dirs_exist_ok=True)
        for distribution in distributions():
            destination = licenses / 'python-packages' / distribution.metadata['Name']
            destination.mkdir(parents=True, exist_ok=True)
            (destination / 'METADATA.txt').write_text(str(distribution.metadata), encoding='utf-8')
            for file in distribution.files or ():
                if any(word in file.name.lower() for word in ('license', 'copying', 'notice')):
                    source = Path(distribution.locate_file(file))
                    if source.is_file():
                        target = destination / str(file).replace('/', '_').replace('\\', '_')
                        shutil.copy2(source, target)
        # Install only Chromium (headed and headless). The recorder and tracker
        # currently use different Playwright revisions, so include both.
        env = {**os.environ, 'PLAYWRIGHT_BROWSERS_PATH': str(browsers), 'PLAYWRIGHT_SKIP_BROWSER_GC': '1'}
        if args.browser_cache:
            for folder in args.browser_cache.iterdir():
                if folder.is_dir() and folder.name.startswith(('chromium-', 'chromium_headless_shell-', 'ffmpeg-', 'winldd-')):
                    shutil.copytree(folder, browsers / folder.name, dirs_exist_ok=True, symlinks=True)
        run([sys.executable, '-m', 'playwright', 'install', 'chromium'], env=env)
        import playwright
        node = Path(playwright.__file__).parent / 'driver' / ('node.exe' if sys.platform == 'win32' else 'node')
        run([node, ROOT / 'node_modules' / 'playwright' / 'cli.js', 'install', 'chromium'], env=env)
        run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', ROOT / 'packaging' / 'AutoEventTracker.spec'])
    mac = sys.platform == 'darwin'
    app_root = ROOT / 'dist' / ('AutoEventTracker.app' if mac else 'AutoEventTracker')
    resource_root = app_root / ('Contents/Resources' if mac else '_internal')
    shutil.copytree(browsers, resource_root / 'browsers', dirs_exist_ok=True, symlinks=True,
                    ignore=shutil.ignore_patterns('.links', '.DS_Store'))
    if mac:
        link = app_root / 'Contents' / 'Frameworks' / 'browsers'
        if not link.exists():
            link.symlink_to('../Resources/browsers', target_is_directory=True)
        run(['codesign', '--force', '--sign', '-', '--timestamp=none', app_root])
    assert_no_project(app_root)
    # Remove PATH entries for Python/Node and run from a fresh working directory.
    worker = app_root / ('Contents/MacOS/AutoEventTrackerWorker' if mac else 'AutoEventTrackerWorker.exe')
    with tempfile.TemporaryDirectory(prefix='aet-clean-install-') as temp:
        env = {**os.environ, 'AET_DATA_DIR': str(Path(temp) / 'user data'), 'QT_QPA_PLATFORM': 'offscreen'}
        env['PATH'] = '/usr/bin:/bin' if mac else os.path.join(os.environ['SystemRoot'], 'System32')
        env.pop('PYTHONPATH', None)
        env.pop('NODE_PATH', None)
        result = installers / f'smoke-{platform.system()}-{platform.machine()}.json'
        try:
            run([worker, '--self-test', result], cwd=temp, env=env, timeout=300)
        finally:
            if result.exists():
                print(result.read_text(encoding='utf-8'), flush=True)
        if not json.loads(result.read_text(encoding='utf-8'))['ok']:
            raise RuntimeError('Bundled application self-test failed')
    if mac:
        installer = installers / f'AutoEventTracker-{VERSION}-macos-{platform.machine()}.pkg'
        package_root = ROOT / 'build' / 'pkg-root'
        shutil.copytree(app_root, package_root / 'Applications' / app_root.name, dirs_exist_ok=True, symlinks=True)
        components = ROOT / 'build' / 'components.plist'
        run(['pkgbuild', '--analyze', '--root', package_root, components])
        data = plistlib.loads(components.read_bytes())
        for component in data:
            component['BundleIsRelocatable'] = False
        components.write_bytes(plistlib.dumps(data))
        run(['pkgbuild', '--root', package_root, '--component-plist', components,
             '--identifier', 'com.exture.autoeventtracker', '--version', VERSION,
             '--install-location', '/', installer])
        listing = subprocess.check_output(['pkgutil', '--payload-files', str(installer)], text=True)
        if any('project' in Path(line).parts for line in listing.splitlines()):
            raise RuntimeError('Project directory found in package payload')
    elif sys.platform == 'win32':
        iscc = shutil.which('ISCC') or str(Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Inno Setup 6' / 'ISCC.exe')
        run([iscc, f'/DAppVersion={VERSION}', ROOT / 'packaging' / 'windows.iss'])
        installer = installers / f'AutoEventTracker-{VERSION}-windows-x64-setup.exe'
    else:
        raise RuntimeError('Run this script on macOS or Windows')
    digest = hashlib.sha256()
    with installer.open('rb') as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b''):
            digest.update(chunk)
    installer.with_suffix(installer.suffix + '.sha256').write_text(f'{digest.hexdigest()}  {installer.name}\n')
    print(f'Installer ready: {installer} ({installer.stat().st_size / 1024**2:.1f} MiB)')


if __name__ == '__main__':
    main()
