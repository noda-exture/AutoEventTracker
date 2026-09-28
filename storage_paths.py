import json
import os
import re
from datetime import datetime


_INVALID_FILE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_COMPACT_TIMESTAMP = re.compile(r"(?<!\d)(\d{12})(?!\d)")
_LEGACY_TIMESTAMP = re.compile(r"(?<!\d)(\d{8})_(\d{4})(?!\d)")


def safe_file_component(value, fallback="scenario"):
    """Return a filesystem-safe single path component while preserving Japanese text."""
    component = _INVALID_FILE_CHARS.sub("_", str(value or "")).strip().strip(".")
    return component or fallback


def scenario_name_from_reference(value):
    reference = str(value or "").replace("\\", "/")
    name = os.path.splitext(os.path.basename(reference))[0]
    if name.endswith("_result"):
        name = name[:-len("_result")]
    return safe_file_component(name)


def scenario_definition_files(scenario_dir):
    """List scenario definition JSON files recursively, excluding captured measurement data."""
    if not os.path.isdir(scenario_dir):
        return []

    definitions = []
    for root, _, filenames in os.walk(scenario_dir):
        for filename in filenames:
            if not filename.lower().endswith(".json"):
                continue
            parent_name = os.path.basename(root)
            if re.fullmatch(rf"{re.escape(parent_name)}_\d{{12}}\.json", filename):
                continue
            path = os.path.join(root, filename)
            try:
                with open(path, "r", encoding="utf-8") as file:
                    data = json.load(file)
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict) or not ("steps" in data or "include_parts" in data):
                continue
            definitions.append(os.path.relpath(path, scenario_dir))
    return sorted(definitions)


def measurement_output_path(project_dir, scenario_name, captured_at=None):
    timestamp = captured_at or datetime.now().strftime("%Y%m%d%H%M")
    safe_scenario_name = safe_file_component(scenario_name)
    output_dir = os.path.join(project_dir, "scenario", safe_scenario_name)
    filename = f"{safe_scenario_name}_{timestamp}.json"
    return os.path.join(output_dir, filename)


def _normalize_timestamp(value):
    digits = re.sub(r"\D", "", str(value or ""))
    return digits[:12] if len(digits) >= 12 else ""


def _timestamp_from_filename(path):
    filename = os.path.basename(path)
    compact_matches = _COMPACT_TIMESTAMP.findall(filename)
    if compact_matches:
        return compact_matches[-1]
    legacy_match = _LEGACY_TIMESTAMP.search(filename)
    if legacy_match:
        return "".join(legacy_match.groups())
    return ""


def measurement_metadata(path):
    """Read the scenario name and minute timestamp used for an Excel comparison name."""
    if not path:
        return None

    normalized_path = os.path.abspath(os.path.expanduser(str(path).strip().strip("'").strip('"')))
    if not os.path.isfile(normalized_path):
        return None

    try:
        with open(normalized_path, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(data, dict):
        return None

    scenario_name = data.get("scenario_name") or scenario_name_from_reference(data.get("scenario"))
    timestamp = _normalize_timestamp(data.get("captured_at")) or _timestamp_from_filename(normalized_path)
    if not timestamp:
        timestamp = datetime.fromtimestamp(os.path.getmtime(normalized_path)).strftime("%Y%m%d%H%M")
    return {
        "scenario_name": safe_file_component(scenario_name),
        "timestamp": timestamp,
    }


def comparison_output_filename(latest_json_path, base_json_path):
    latest = measurement_metadata(latest_json_path)
    base = measurement_metadata(base_json_path)
    if not latest or not base:
        return ""
    return (
        f"{latest['scenario_name']}_{latest['timestamp']}"
        f"_vs_{base['timestamp']}.xlsx"
    )
