"""Separate read-only application resources from user-created project data."""
import os
from pathlib import Path
import shutil
import sys


APP_NAME = "AutoEventTracker"


def is_bundled():
    return bool(getattr(sys, "frozen", False))


def resource_path(*parts):
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return root.joinpath(*parts)


def data_directory():
    override = os.environ.get("AET_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if not is_bundled():
        return Path(__file__).resolve().parent
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / APP_NAME
    return Path.home() / ".local" / "share" / APP_NAME


def global_config_path():
    return data_directory() / "global_config.json"


def initialize_runtime():
    root = data_directory()
    root.mkdir(parents=True, exist_ok=True)
    if is_bundled():
        # The distribution contains no project directory. Create one on first
        # launch and seed only a freshly generated, generic report template.
        (root / "project").mkdir(exist_ok=True)
        for source, destination in (
            (resource_path("global_config.json"), root / "global_config.json"),
            (resource_path("defaults", "template.xlsx"), root / "project" / "template.xlsx"),
        ):
            if not destination.exists():
                shutil.copy2(source, destination)
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(resource_path("browsers"))
    os.environ["AET_DATA_DIR"] = str(root)
    os.environ["AET_GLOBAL_CONFIG"] = str(root / "global_config.json")
    os.chdir(root)
    return root


def tracker_command():
    if is_bundled():
        suffix = ".exe" if sys.platform == "win32" else ""
        return [str(Path(sys.executable).with_name(APP_NAME + "Worker" + suffix)), "--run-tracker"]
    return [sys.executable, "-u", str(resource_path("tracker.py"))]


def recorder_command():
    if is_bundled():
        # Playwright ships a standalone Node runtime on every supported OS.
        node = resource_path("playwright", "driver", "node.exe" if sys.platform == "win32" else "node")
    else:
        node = "node"
    return [str(node), str(resource_path("record.js"))]


def child_process_options():
    options = {"env": {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}}
    if sys.platform == "win32":
        import subprocess
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    return options
