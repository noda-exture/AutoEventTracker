import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from openpyxl import Workbook, load_workbook

from display_parts import Ui_MainWindow
from excel_reporter import generate_compare_report
from main import AutoTrackerApp


class SingleReportTests(unittest.TestCase):
    def test_single_report_has_values_without_comparison_rows_or_rules(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            wb = Workbook()
            sheet = wb.active
            sheet.title = 'GA4'
            sheet.append([])
            sheet.append(['GA4パラメータ', '種別', '型', '項目', '説明'])
            sheet.append(['en', '', '', 'イベント名', ''])
            wb.save(project / 'template.xlsx')
            data = {'events': [{'type': 'GA4', 'step_index': 0, 'step_id': '0001',
                                'params': {'en': 'page_view', 'tid': 'G-TEST'}}]}
            latest = project / 'latest.json'
            latest.write_text(json.dumps(data))
            result = generate_compare_report(str(project), str(latest), None, 'single.xlsx', logger_func=lambda _: None)
            report = load_workbook(result)
            sheet = report['GA4']
            self.assertEqual(sheet['F3'].value, 'page_view')
            self.assertEqual(len(sheet.conditional_formatting), 0)
            text = '\n'.join(str(cell.value or '') for row in sheet for cell in row)
            for marker in ('過去データ', '比較元になし', '最新のみ', '比較元のみ'):
                self.assertNotIn(marker, text)
            report.close()

    def test_toggle_disables_baseline_and_switches_output_name(self):
        app = QApplication.instance() or QApplication([])
        ui = Ui_MainWindow()
        tab = ui._create_analysis_tab()
        owner = SimpleNamespace(ui=ui)
        ui.txt_f1.setText('/tmp/latest.json')
        ui.txt_f2.setText('/tmp/baseline.json')
        self.assertTrue(ui.chk_compare.isChecked())
        self.assertFalse(ui.comparison_input.isHidden())
        ui.chk_compare.setChecked(False)
        AutoTrackerApp.update_comparison_output_name(owner)
        self.assertFalse(ui.comparison_input.isHidden())
        self.assertFalse(ui.txt_f2.isEnabled())
        self.assertFalse(ui.btn_f2.isEnabled())
        self.assertEqual(ui.txt_out.text(), 'latest.xlsx')
        self.assertEqual(ui.lbl_analysis_input.text(), '計測データ')
        ui.chk_compare.setChecked(True)
        self.assertFalse(ui.comparison_input.isHidden())
        self.assertTrue(ui.txt_f2.isEnabled())
        self.assertTrue(ui.btn_f2.isEnabled())
        self.assertEqual(ui.txt_f2.text(), '/tmp/baseline.json')
        self.assertEqual(ui.btn_run_analysis.text(), 'レポートを生成')
        tab.close()


if __name__ == '__main__':
    unittest.main()
