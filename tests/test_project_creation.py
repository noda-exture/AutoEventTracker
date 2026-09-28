import os
import tempfile
import unittest

from main import copy_default_template, normalize_trash_result, resolve_project_directory


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
