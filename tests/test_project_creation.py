import json
import os
import tempfile
import unittest
from datetime import datetime

from main import (
    append_project_log,
    copy_default_template,
    ensure_project_directories,
    format_project_settings,
    normalize_trash_result,
    resolve_project_directory,
)


class ProjectCreationTests(unittest.TestCase):
    def test_default_template_is_copied_into_project(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            template_path = os.path.join(temp_dir, "template.xlsx")
            project_dir = os.path.join(temp_dir, "sample_project")
            os.makedirs(project_dir)
            with open(template_path, "wb") as file:
                file.write(b"sample-template")

            copied_path = copy_default_template(project_dir, template_path)

            self.assertEqual(copied_path, os.path.join(project_dir, "template.xlsx"))
            with open(copied_path, "rb") as file:
                self.assertEqual(file.read(), b"sample-template")

    def test_missing_default_template_raises_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = os.path.join(temp_dir, "sample_project")
            os.makedirs(project_dir)
            with self.assertRaises(FileNotFoundError):
                copy_default_template(project_dir, os.path.join(temp_dir, "missing.xlsx"))

    def test_project_directories_include_daily_logs_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = os.path.join(temp_dir, "sample_project")
            ensure_project_directories(project_dir)
            for folder_name in ("outputs", "scenario", "logs"):
                self.assertTrue(os.path.isdir(os.path.join(project_dir, folder_name)))

    def test_project_log_is_appended_to_daily_file(self):
        with tempfile.TemporaryDirectory() as project_root:
            project_dir = os.path.join(project_root, "sample")
            ensure_project_directories(project_dir)
            log_time = datetime(2026, 9, 28, 12, 30)

            log_path = append_project_log("sample", "first", project_root, log_time)
            append_project_log("sample", "second\n", project_root, log_time)

            self.assertEqual(
                os.path.realpath(log_path),
                os.path.realpath(os.path.join(project_dir, "logs", "20260928.log")),
            )
            with open(log_path, "r", encoding="utf-8") as file:
                self.assertEqual(file.read(), "first\nsecond\n")

    def test_project_log_starts_on_new_line_when_existing_file_has_no_newline(self):
        with tempfile.TemporaryDirectory() as project_root:
            project_dir = os.path.join(project_root, "sample")
            ensure_project_directories(project_dir)
            log_path = os.path.join(project_dir, "logs", "20260928.log")
            with open(log_path, "w", encoding="utf-8") as file:
                file.write("existing")

            append_project_log(
                "sample",
                "appended",
                project_root,
                datetime(2026, 9, 28, 12, 30),
            )

            with open(log_path, "r", encoding="utf-8") as file:
                self.assertEqual(file.read(), "existing\nappended\n")

    def test_project_settings_log_contains_project_and_config_values(self):
        formatted = format_project_settings(
            "sample",
            {
                "client_name": "サンプル株式会社",
                "task_name": "計測確認",
                "environments": {"dev": "https://dev.example.com"},
            },
        )
        settings = json.loads(formatted)
        self.assertEqual(settings["project_id"], "sample")
        self.assertEqual(settings["client_name"], "サンプル株式会社")
        self.assertEqual(settings["environments"]["dev"], "https://dev.example.com")

    def test_project_directory_must_be_directly_under_project_root(self):
        with tempfile.TemporaryDirectory() as project_root:
            self.assertEqual(
                resolve_project_directory("sample", project_root),
                os.path.realpath(os.path.join(project_root, "sample")),
            )
            with self.assertRaises(ValueError):
                resolve_project_directory("../outside", project_root)

    def test_trash_result_supports_boolean_return_value(self):
        self.assertEqual(normalize_trash_result(True), (True, ""))
        self.assertEqual(normalize_trash_result(False), (False, ""))

    def test_trash_result_supports_tuple_return_value(self):
        self.assertEqual(
            normalize_trash_result((True, "/Trash/sample")),
            (True, "/Trash/sample"),
        )


if __name__ == "__main__":
    unittest.main()
