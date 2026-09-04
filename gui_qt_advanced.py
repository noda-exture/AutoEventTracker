import os
import sys
import json
import threading
import subprocess
from datetime import datetime

from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QFileDialog
from PySide6.QtCore import Signal, QThread
from PySide6.QtGui import QTextCursor

from excel_reporter import generate_compare_report
from ui_main import Ui_MainWindow

# ==========================================
# ⚙️ 非同期処理ワーカー
# ==========================================

class ReporterWorker(threading.Thread):
    def __init__(self, proj, f1, f2, out, log_signal, finish_signal, err_signal):
        super().__init__()
        self.proj = proj
        self.f1 = f1
        self.f2 = f2
        self.out = out
        self.log_signal = log_signal
        self.finish_signal = finish_signal
        self.err_signal = err_signal

    def run(self):
        try:
            res = generate_compare_report(self.proj, self.f1, self.f2, self.out, 
                                          logger_func=lambda m: self.log_signal.emit(m))
            self.finish_signal.emit(str(res) if res else "")
        except Exception as e:
            self.err_signal.emit(str(e))

class ScenarioWorker(QThread):
    log = Signal(str)
    finished = Signal(bool)

    def __init__(self, proj, scenario_file, headless):
        super().__init__()
        self.proj = proj
        self.scenario_file = scenario_file
        self.headless = headless

    def run(self):
        try:
            cmd = [sys.executable, "tracker.py", self.proj, self.scenario_file]
            if self.headless:
                cmd.append("--headless")

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                bufsize=1
            )
            for line in iter(process.stdout.readline, ''):
                if line:
                    self.log.emit(line)
            process.stdout.close()
            return_code = process.wait()
            self.finished.emit(return_code == 0)
        except Exception as e:
            self.log.emit(f"\n❌ 実行エラー: {str(e)}\n")
            self.finished.emit(False)

class AutoRecordWorker(QThread):
    log = Signal(str)
    finished = Signal(bool)

    def __init__(self, proj, filename, start_url):
        super().__init__()
        self.proj = proj
        self.filename = filename
        self.start_url = start_url

    def run(self):
        try:
            process = subprocess.Popen(
                ["node", "record.js", self.proj, self.filename, self.start_url],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                bufsize=1
            )
            for line in iter(process.stdout.readline, ''):
                if line:
                    self.log.emit(line)
            process.stdout.close()
            return_code = process.wait()
            self.finished.emit(return_code == 0)
        except Exception as e:
            self.log.emit(f"\n❌ 実行エラー (node または record.js が見つかりません): {str(e)}\n")
            self.finished.emit(False)


# ==========================================
# 🖥️ メインアプリケーション
# ==========================================

class AutoTrackerApp(QMainWindow):
    sig_log = Signal(str)
    sig_finish = Signal(str)
    sig_err = Signal(str)

    def __init__(self):
        super().__init__()
        # UIの読み込みとセットアップ
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        # シグナル接続
        self.sig_log.connect(self.log_write)
        self.sig_finish.connect(self.on_analysis_finished)
        self.sig_err.connect(self.on_analysis_error)

        # イベントハンドラのバインド
        self._bind_events()

        # 初期化
        self.refresh_project_list()

    def _bind_events(self):
        # 画面切替 / プロジェクト選択
        self.ui.btn_create_proj.clicked.connect(lambda: self.ui.stacked_widget.setCurrentIndex(1))
        self.ui.btn_cancel_proj.clicked.connect(lambda: self.ui.stacked_widget.setCurrentIndex(0))
        self.ui.btn_confirm_proj.clicked.connect(self.create_project_action)

        self.ui.combo_proj.currentTextChanged.connect(self.update_scenario_list)
        self.ui.combo_scenario.currentTextChanged.connect(self.load_scenario_info)

        # 分析タブ
        self.ui.btn_f1.clicked.connect(lambda: self.select_file(self.ui.txt_f1))
        self.ui.btn_f2.clicked.connect(lambda: self.select_file(self.ui.txt_f2))
        self.ui.btn_run_analysis.clicked.connect(self.start_analysis)
        self.ui.btn_open.clicked.connect(self.open_dir)

        # 実行タブ
        self.ui.btn_exec_scenario.clicked.connect(self.start_scenario_execution)

        # 作成タブ
        self.ui.btn_record_auto.clicked.connect(self.start_auto_record)

    # ==========================================
    # ⚙️ ロジック・イベント処理
    # ==========================================
    def refresh_project_list(self):
        projects = [f for f in os.listdir("project") if os.path.isdir(os.path.join("project", f))] if os.path.exists("project") else []
        self.ui.combo_proj.clear()
        if projects:
            self.ui.combo_proj.addItems(projects)
            self.update_scenario_list(projects[0])

    def update_scenario_list(self, proj_name):
        self.ui.combo_scenario.clear()
        if not proj_name: return
        
        scenario_dir = os.path.join("project", proj_name, "scenario")
        if os.path.exists(scenario_dir):
            files = [f for f in os.listdir(scenario_dir) if f.endswith('.json')]
            if files:
                self.ui.combo_scenario.addItems(files)
            else:
                self.ui.combo_scenario.addItem("※ シナリオJSONがありません")
        else:
            self.ui.combo_scenario.addItem("※ scenarioフォルダがありません")

    def load_scenario_info(self, scenario_file):
        if not scenario_file or scenario_file.startswith("※"):
            self.ui.lbl_info_name.setText("-")
            self.ui.lbl_info_url.setText("-")
            self.ui.lbl_info_memo.setText("-")
            return
            
        proj = self.ui.combo_proj.currentText()
        json_path = os.path.join("project", proj, "scenario", scenario_file)
        
        try:
            if os.path.exists(json_path):
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                self.ui.lbl_info_name.setText(data.get("scenario_name", scenario_file.replace(".json", "")))
                self.ui.lbl_info_url.setText(data.get("start_url", "未設定"))
                self.ui.lbl_info_memo.setText(data.get("memo", "（メモ項目なし）"))
            else:
                raise FileNotFoundError()
        except Exception:
            self.ui.lbl_info_name.setText(scenario_file)
            self.ui.lbl_info_url.setText("読み込み失敗")
            self.ui.lbl_info_memo.setText("JSONの解析に失敗したか、ファイルが見つかりません。")

    def create_project_action(self):
        proj_id = self.ui.input_proj_id.text().strip()
        client = self.ui.input_client.text().strip() or "クライアント名未設定"
        task = self.ui.input_task.text().strip() or "課題名未設定"

        if not proj_id:
            QMessageBox.warning(self, "エラー", "フォルダ名を入力してください。")
            return

        proj_dir = os.path.join("project", proj_id)
        if os.path.exists(proj_dir):
            QMessageBox.warning(self, "エラー", f"既に '{proj_id}' というプロジェクトが存在します。")
            return

        os.makedirs(os.path.join(proj_dir, "outputs"), exist_ok=True)
        os.makedirs(os.path.join(proj_dir, "scenario"), exist_ok=True)
        os.makedirs(os.path.join(proj_dir, "parts"), exist_ok=True)

        config_data = {
            "client_name": client,
            "task_name": task,
            "excel_setting": {
                "font_name": "游ゴシック", "theme_color_new": "E2EFDA", "theme_color_old": "FFF2CC", "diff_color": "FFC7CE", "diff_font_color": "9C0006"
            },
            "extraction_rules": {
                "ignore_params": ["_ts", "gtm_auth", "gjid", "gtm", "requestId", "configId"], "nested_separator": "."
            }
        }
        with open(os.path.join(proj_dir, "config.json"), "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4, ensure_ascii=False)

        self.ui.input_proj_id.clear()
        self.ui.input_client.clear()
        self.ui.input_task.clear()
        self.refresh_project_list()
        
        index = self.ui.combo_proj.findText(proj_id)
        if index >= 0: self.ui.combo_proj.setCurrentIndex(index)

        QMessageBox.information(self, "成功", f"プロジェクト '{proj_id}' を作成しました！")
        self.ui.stacked_widget.setCurrentIndex(0)

    def log_write(self, msg):
        self.ui.txt_log.moveCursor(QTextCursor.End)
        self.ui.txt_log.insertPlainText(msg)
        self.ui.txt_log.verticalScrollBar().setValue(self.ui.txt_log.verticalScrollBar().maximum())

    def select_file(self, target_lineedit):
        proj = self.ui.combo_proj.currentText()
        init_dir = os.path.abspath(os.path.join("project", proj, "outputs")) if os.path.exists(os.path.join("project", proj, "outputs")) else os.getcwd()
        path, _ = QFileDialog.getOpenFileName(self, "JSONファイルを選択", init_dir, "JSON Files (*.json)")
        if path: target_lineedit.setText(path)

    def open_dir(self):
        proj = self.ui.combo_proj.currentText()
        output_dir = os.path.abspath(os.path.join("project", proj, "outputs"))
        os.makedirs(output_dir, exist_ok=True)
        if sys.platform == "win32": os.startfile(output_dir)
        elif sys.platform == "darwin": subprocess.call(["open", output_dir])

    def start_analysis(self):
        proj = self.ui.combo_proj.currentText()
        f1 = self.ui.txt_f1.text().strip().strip("'").strip('"')
        f2 = self.ui.txt_f2.text().strip().strip("'").strip('"')
        out = self.ui.txt_out.text().strip()

        if not f1 or not f2 or not out:
            QMessageBox.warning(self, "入力エラー", "すべての項目を入力・選択してください。")
            return
        if not out.lower().endswith(".xlsx"):
            out += ".xlsx"
            self.ui.txt_out.setText(out)

        self.ui.btn_run_analysis.setEnabled(False)
        self.ui.progress.setVisible(True)
        self.ui.txt_log.clear()
        self.log_write(f"⏳ [{datetime.now().strftime('%H:%M:%S')}] 分析(突合)処理を開始します...\n")

        self.analysis_worker = ReporterWorker(proj, f1, f2, out, self.sig_log, self.sig_finish, self.sig_err)
        self.analysis_worker.start()

    def on_analysis_finished(self, result_path):
        self.ui.btn_run_analysis.setEnabled(True)
        self.ui.progress.setVisible(False)
        self.log_write("✨ すべての処理が正常に完了しました！\n")
        if result_path and os.path.exists(result_path):
            if sys.platform == "win32": os.startfile(result_path)
            elif sys.platform == "darwin": subprocess.call(["open", result_path])

    def on_analysis_error(self, err_msg):
        self.ui.btn_run_analysis.setEnabled(True)
        self.ui.progress.setVisible(False)
        self.log_write(f"❌ エラーが発生しました:\n{err_msg}\n")
        QMessageBox.critical(self, "エラー", f"エラーが発生しました:\n{err_msg}")

    # --- 🚀 シナリオ実行処理 ---
    def start_scenario_execution(self):
        proj = self.ui.combo_proj.currentText()
        scenario_file = self.ui.combo_scenario.currentText()
        
        if not scenario_file or scenario_file.startswith("※"):
            QMessageBox.warning(self, "エラー", "実行可能なシナリオが選択されていません。")
            return
            
        self.ui.btn_exec_scenario.setEnabled(False)
        self.ui.txt_log.clear()
        
        headless_mode = self.ui.chk_headless.isChecked()
        mode_str = "【ヘッドレスモード】" if headless_mode else "【通常モード (画面表示)】"
        
        self.log_write(f"⏳ [{datetime.now().strftime('%H:%M:%S')}] シナリオ実行を開始します: {scenario_file} {mode_str}\n")
        self.log_write("==================================================\n")
        
        self.scenario_worker = ScenarioWorker(proj, scenario_file, headless_mode)
        self.scenario_worker.log.connect(self.log_write)
        self.scenario_worker.finished.connect(self.on_scenario_finished)
        self.scenario_worker.start()
        
    def on_scenario_finished(self, success):
        self.ui.btn_exec_scenario.setEnabled(True)
        self.log_write("==================================================\n")
        if success:
            self.log_write("✨ シナリオの実行が完了しました！出力結果(JSON)は outputs フォルダを確認してください。\n")

    # --- ⏺️ 自動シナリオレコーダー 処理 ---
    def start_auto_record(self):
        proj = self.ui.combo_proj.currentText()
        filename = self.ui.txt_scenario_file_auto.text().strip()
        url = self.ui.txt_url_auto.text().strip()
        
        if not proj:
            QMessageBox.warning(self, "エラー", "対象プロジェクトが選択されていません。")
            return
        if not filename:
            QMessageBox.warning(self, "エラー", "保存するシナリオファイル名を入力してください。")
            return
        if not url:
            QMessageBox.warning(self, "エラー", "開始URLを入力してください。")
            return
            
        if not filename.endswith(".json"):
            filename += ".json"
            
        self.ui.btn_record_auto.setEnabled(False)
        self.ui.txt_log.clear()
        self.log_write(f"⏳ [{datetime.now().strftime('%H:%M:%S')}] 自動レコーダー を起動します...\n")
        self.log_write(f"🔗 開始URL: {url}\n")
        self.log_write(f"📁 保存先: project/{proj}/scenario/{filename}\n")
        self.log_write("==================================================\n")
        self.log_write("💡 起動したブラウザで操作を行い、終わったらブラウザを閉じてください。\n")
        
        self.record_worker = AutoRecordWorker(proj, filename, url)
        self.record_worker.log.connect(self.log_write)
        self.record_worker.finished.connect(lambda s, p=proj: self.on_record_finished(s, p))
        self.record_worker.start()
        
    def on_record_finished(self, success, proj):
        self.ui.btn_record_auto.setEnabled(True)
        self.log_write("==================================================\n")
        if success:
            self.log_write("✨ シナリオの自動記録と保存が完了しました！実行タブから確認できます。\n")
            self.update_scenario_list(proj)
        else:
            self.log_write("⚠️ レコーダーが終了しましたが、エラーが発生した可能性があります。\n")

# スタイルシート読み込み補助関数
def load_stylesheet(app, qss_filename="styles.qss"):
    if os.path.exists(qss_filename):
        with open(qss_filename, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())

if __name__ == "__main__":
    app = QApplication(sys.argv)
    load_stylesheet(app, "styles.qss")
    window = AutoTrackerApp()
    window.show()
    sys.exit(app.exec())