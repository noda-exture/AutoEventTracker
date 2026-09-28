import json
import os
import tempfile
import unittest

from storage_paths import (
    comparison_output_filename,
    measurement_metadata,
    measurement_output_path,
    scenario_definition_files,
)


class StoragePathTests(unittest.TestCase):
    def test_measurement_output_is_saved_under_scenario_name(self):
        path = measurement_output_path(
            os.path.join("project", "sample"),
            "purchase_flow",
            "202609281430",
        )
        self.assertEqual(
            path,
            os.path.join(
                "project",
                "sample",
                "scenario",
                "purchase_flow",
                "purchase_flow_202609281430.json",
            ),
        )

    def test_scenario_definition_files_excludes_measurement_json(self):
        with tempfile.TemporaryDirectory() as scenario_dir:
            nested_dir = os.path.join(scenario_dir, "purchase_flow")
            os.makedirs(nested_dir)
            with open(os.path.join(nested_dir, "purchase_flow.json"), "w", encoding="utf-8") as file:
                json.dump({"start_url": "https://example.com", "steps": []}, file)
            with open(
                os.path.join(nested_dir, "purchase_flow_202609281430.json"),
                "w",
                encoding="utf-8",
            ) as file:
                json.dump({"scenario_name": "purchase_flow", "events": []}, file)

            self.assertEqual(
                scenario_definition_files(scenario_dir),
                [os.path.join("purchase_flow", "purchase_flow.json")],
            )

    def test_comparison_filename_uses_latest_scenario_and_both_dates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            latest = os.path.join(temp_dir, "purchase_flow_202609281430.json")
            base = os.path.join(temp_dir, "purchase_flow_202609271200.json")
            for path, captured_at in ((latest, "202609281430"), (base, "202609271200")):
                with open(path, "w", encoding="utf-8") as file:
                    json.dump(
                        {"scenario_name": "purchase_flow", "captured_at": captured_at, "events": []},
                        file,
                    )

            self.assertEqual(
                comparison_output_filename(latest, base),
                "purchase_flow_202609281430_vs_202609271200.xlsx",
            )

    def test_legacy_measurement_filename_is_supported(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "20260925_1135_car_result.json")
            with open(path, "w", encoding="utf-8") as file:
                json.dump({"scenario": "car.json", "events": []}, file)

            self.assertEqual(
                measurement_metadata(path),
                {"scenario_name": "car", "timestamp": "202609251135"},
            )


if __name__ == "__main__":
    unittest.main()
