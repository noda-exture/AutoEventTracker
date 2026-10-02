import os
import sys
import json
import shutil
import threading
import subprocess
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit

from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QFileDialog
from PySide6.QtCore import QFile, Signal, QThread
from PySide6.QtGui import QTextCursor

from excel_reporter import generate_compare_report
from display_parts import Ui_MainWindow
from global_settings import load_global_config, resolve_device, load_recording_viewport, validate_recording_viewport
from storage_paths import (
    comparison_output_filename,
    safe_file_component,
    scenario_definition_files,
    scenario_name_from_reference,
)


def parse_environment_lines(text):
    """Parse one `name = base URL` environment per line."""
    environments = {}
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if "=" not in line:
            raise ValueError(f"{line_number}行目は「環境名 = URL」の形式で入力してください。")
        name, base_url = (part.strip() for part in line.split("=", 1))
        parsed = urlsplit(base_url)
        if not name:
            raise ValueError(f"{line_number}行目の環境名が空です。")
        if name in environments:
            raise ValueError(f"環境名『{name}』が重複しています。")
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(f"{line_number}行目のURLが不正です: {base_url}")
        environments[name] = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    return environments


def environment_lines(environments):
    if not isinstance(environments, dict):
        return ""
    lines = []
    for name, value in environments.items():
        base_url = value.get("base_url", "") if isinstance(value, dict) else value
        if name and base_url:
            lines.append(f"{name} = {base_url}")
    return "\n".join(lines)


def replace_start_url_origin(start_url, base_url):
    source = urlsplit(start_url)
    target = urlsplit(base_url)
    if source.scheme not in ("http", "https") or not source.netloc:
        raise ValueError("シナリオの開始URLが設定されていません。")
    if target.scheme not in ("http", "https") or not target.netloc:
        raise ValueError("登録環境のURLが不正です。")
    return urlunsplit((target.scheme, target.netloc, source.path, source.query, source.fragment))


def copy_default_template(project_dir, template_path=None):
    source_path = template_path or os.path.join("project", "template.xlsx")
    if not os.path.isfile(source_path):
        raise FileNotFoundError(f"共通テンプレートが見つかりません: {source_path}")
    target_path = os.path.join(project_dir, "template.xlsx")
    shutil.copy2(source_path, target_path)
    return target_path


def resolve_project_directory(project_name, project_root="project"):
    root_path = os.path.realpath(project_root)
    target_path = os.path.realpath(os.path.join(root_path, project_name))
    if os.path.dirname(target_path) != root_path:
        raise ValueError("削除対象のプロジェクトパスが不正です。")
    return target_path


def ensure_project_directories(project_dir):
    for folder_name in ("outputs", "scenario", "logs"):
        os.makedirs(os.path.join(project_dir, folder_name), exist_ok=True)


def append_project_log(project_name, message, project_root="project", now=None):
    if not project_name or not str(message).strip():
        return ""

    project_dir = resolve_project_directory(project_name, project_root)
    if not os.path.isdir(project_dir):
        return ""

    logs_dir = os.path.join(project_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    log_date = (now or datetime.now()).strftime("%Y%m%d")
    log_path = os.path.join(logs_dir, f"{log_date}.log")

    prefix = ""
    if os.path.isfile(log_path) and os.path.getsize(log_path) > 0:
        with open(log_path, "rb") as existing_log:
            existing_log.seek(-1, os.SEEK_END)
            if existing_log.read(1) != b"\n":
                prefix = "\n"

    entry = str(message).rstrip("\r\n")
    with open(log_path, "a", encoding="utf-8") as log_file:
        log_file.write(f"{prefix}{entry}\n")
    return log_path


def format_project_settings(project_id, config):
    settings = {"project_id": project_id}
    if isinstance(config, dict):
        settings.update(config)
    return json.dumps(settings, ensure_ascii=False, indent=2, sort_keys=True)


def normalize_trash_result(result):
    """Support both PySide6 return shapes for QFile.moveToTrash()."""
    if isinstance(result, tuple):
        moved = bool(result[0]) if result else False
        trash_path = str(result[1]) if len(result) > 1 and result[1] else ""
        return moved, trash_path
    return bool(result), ""

# ==========================================
# 非同期処理ワーカー
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

    def __init__(self, proj, scenario_file, headless, environment=None, start_url_override=None, device=None):
        super().__init__()
        self.proj = proj
        self.scenario_file = scenario_file
        self.headless = headless
        self.environment = environment
        self.start_url_override = start_url_override
        self.device = device

    def run(self):
        try:
            cmd = [sys.executable, "tracker.py", self.proj, self.scenario_file]
            if self.headless:
                cmd.append("--headless")
            if self.device is not None:
                cmd.extend(["--device", self.device])
            if self.environment:
                cmd.extend(["--environment", self.environment])
            if self.start_url_override:
                cmd.extend(["--start-url", self.start_url_override])

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
            self.log.emit(f"\n実行エラー: {str(e)}\n")
            self.finished.emit(False)

class AutoRecordWorker(QThread):
    log = Signal(str)
    finished = Signal(bool)

    def __init__(self, proj, filename, start_url, memo, viewport=None):
        super().__init__()
        self.proj = proj
        self.filename = filename
        self.start_url = start_url
        self.memo = memo
        self.viewport = viewport

    def run(self):
        try:
            viewport = validate_recording_viewport(self.viewport) if self.viewport is not None else load_recording_viewport()
            process = subprocess.Popen(
                ["node", "record.js", self.proj, self.filename, self.start_url, self.memo,
                 str(viewport['width']), str(viewport['height'])],
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
            self.log.emit(f"\n実行エラー (node または record.js が見つかりません): {str(e)}\n")
            self.finished.emit(False)


# ==========================================
# メインアプリケーション
# ==========================================

class AutoTrackerApp(QMainWindow):
    sig_log = Signal(str)
    sig_finish = Signal(str)
    sig_err = Signal(str)

    def __init__(self):
        super().__init__()
        self.current_editing_proj = ""
        self.is_edit_mode = False # 新規作成か編集かを示すフラグ
        self.current_scenario_start_url = ""

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
        self.refresh_devices()
        self.refresh_recording_settings()

    def refresh_recording_settings(self):
        try:
            viewport = load_recording_viewport()
        except ValueError as error:
            self.recording_settings_error = str(error)
            self.log_write(f"{error}\n")
            return
        self.recording_settings_error = None
        self.ui.spin_record_width.setValue(viewport['width'])
        self.ui.spin_record_height.setValue(viewport['height'])

    def refresh_devices(self):
        previous = self.ui.combo_device.currentData()
        self.ui.combo_device.clear()
        try:
            config = load_global_config()
        except ValueError as error:
            self.ui.combo_device.addItem("※ デバイス設定を確認してください", None)
            self.ui.combo_device.setToolTip(str(error))
            self.log_write(f"{error}\n")
            return
        for device_id, device in config['devices'].items():
            self.ui.combo_device.addItem(device['name'], device_id)
        selected = previous if previous in config['devices'] else config['default_device']
        self.ui.combo_device.setCurrentIndex(self.ui.combo_device.findData(selected))
        self.ui.combo_device.setToolTip("global_config.jsonに登録したデバイス設定を選択します。")

    def _bind_events(self):
        # 画面切替 / プロジェクト選択
        self.ui.btn_create_proj.clicked.connect(self.open_create_project_page)
        self.ui.btn_edit_proj.clicked.connect(self.open_edit_project_page)
        self.ui.btn_cancel_proj.clicked.connect(lambda: self.ui.stacked_widget.setCurrentIndex(0))
        self.ui.btn_confirm_proj.clicked.connect(self.save_project_action)
        self.ui.btn_delete_proj.clicked.connect(self.delete_project_action)
        self.ui.btn_open_template.clicked.connect(self.open_template_excel)

        self.ui.combo_proj.currentTextChanged.connect(self.update_scenario_list)
        self.ui.combo_scenario.currentTextChanged.connect(self.load_scenario_info)
        self.ui.combo_environment.currentIndexChanged.connect(self.update_effective_url_preview)
        self.ui.chk_override_start_url.toggled.connect(self.on_start_url_override_toggled)
        self.ui.txt_start_url_override.textChanged.connect(self.update_effective_url_preview)

        # 分析タブ
        self.ui.btn_f1.clicked.connect(lambda: self.select_file(self.ui.txt_f1))
        self.ui.btn_f2.clicked.connect(lambda: self.select_file(self.ui.txt_f2))
        self.ui.txt_f1.textChanged.connect(self.update_comparison_output_name)
        self.ui.txt_f2.textChanged.connect(self.update_comparison_output_name)
        self.ui.btn_run_analysis.clicked.connect(self.start_analysis)
        self.ui.btn_open.clicked.connect(self.open_dir)

        # 実行タブ
        self.ui.btn_exec_scenario.clicked.connect(self.start_scenario_execution)

        # 作成タブ
        self.ui.btn_record_auto.clicked.connect(self.start_auto_record)

    # ==========================================
    # ロジック・イベント処理
    # ==========================================
    def refresh_project_list(self):
        projects = [f for f in os.listdir("project") if os.path.isdir(os.path.join("project", f))] if os.path.exists("project") else []
        self.ui.combo_proj.clear()
        if projects:
            self.ui.combo_proj.addItems(projects)
            self.update_scenario_list(projects[0])
            self.ui.btn_edit_proj.setEnabled(True)
        else:
            self.ui.btn_edit_proj.setEnabled(False)

    def update_scenario_list(self, proj_name):
        self.load_project_environments(proj_name)
        self.ui.chk_override_start_url.setChecked(False)
        self.ui.txt_start_url_override.clear()
        self.ui.combo_scenario.clear()
        if not proj_name: return
        
        scenario_dir = os.path.join("project", proj_name, "scenario")
        if os.path.exists(scenario_dir):
            files = scenario_definition_files(scenario_dir)
            if files:
                self.ui.combo_scenario.addItems(files)
            else:
                self.ui.combo_scenario.addItem("※ シナリオJSONがありません")
        else:
            self.ui.combo_scenario.addItem("※ scenarioフォルダがありません")

    def load_scenario_info(self, scenario_file):
        if not self.ui.chk_override_start_url.isChecked():
            self.ui.txt_start_url_override.clear()
            self.ui.txt_start_url_override.setEnabled(False)

        if not scenario_file or scenario_file.startswith("※"):
            self.ui.lbl_info_name.setText("-")
            self.ui.lbl_info_url.setText("-")
            self.ui.lbl_info_memo.setText("-")
            self.ui.lbl_info_effective_url.setText("-")
            self.current_scenario_start_url = ""
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
                self.current_scenario_start_url = data.get("start_url", "")
            else:
                raise FileNotFoundError()
        except Exception:
            self.ui.lbl_info_name.setText(scenario_file)
            self.ui.lbl_info_url.setText("読み込み失敗")
            self.ui.lbl_info_memo.setText("JSONの解析に失敗したか、ファイルが見つかりません。")
            self.current_scenario_start_url = ""
        self.update_effective_url_preview()

    def load_project_environments(self, proj_name):
        current_name = self.ui.combo_environment.currentText()
        self.ui.combo_environment.blockSignals(True)
        self.ui.combo_environment.clear()
        self.ui.combo_environment.addItem("シナリオ設定を使用", "")

        config_path = os.path.join("project", proj_name, "config.json")
        if proj_name and os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as config_file:
                    config = json.load(config_file)
                environments = config.get("environments", {})
                if isinstance(environments, dict):
                    for name, value in environments.items():
                        base_url = value.get("base_url", "") if isinstance(value, dict) else value
                        if name and base_url:
                            self.ui.combo_environment.addItem(name, base_url)
            except (OSError, json.JSONDecodeError, AttributeError):
                pass

        index = self.ui.combo_environment.findText(current_name)
        self.ui.combo_environment.setCurrentIndex(index if index >= 0 else 0)
        self.ui.combo_environment.blockSignals(False)
        self.update_effective_url_preview()

    def selected_execution_url(self):
        if self.ui.chk_override_start_url.isChecked():
            effective_url = self.ui.txt_start_url_override.text().strip()
            if not effective_url:
                raise ValueError("今回使用する開始URLを入力してください。")
        else:
            base_url = self.ui.combo_environment.currentData()
            effective_url = (
                replace_start_url_origin(self.current_scenario_start_url, base_url)
                if base_url else self.current_scenario_start_url
            )

        parsed = urlsplit(effective_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("今回使用する開始URLが不正です。")
        return effective_url

    def update_effective_url_preview(self, *_):
        try:
            effective_url = self.selected_execution_url()
        except ValueError as error:
            effective_url = f"未設定: {error}"
        self.ui.lbl_info_effective_url.setText(effective_url or "-")

    def on_start_url_override_toggled(self, checked):
        if not checked:
            self.ui.txt_start_url_override.clear()
            self.ui.txt_start_url_override.setEnabled(False)
            self.update_effective_url_preview()
            return

        if not self.ui.txt_start_url_override.text().strip():
            base_url = self.ui.combo_environment.currentData()
            try:
                initial_url = (
                    replace_start_url_origin(self.current_scenario_start_url, base_url)
                    if base_url else self.current_scenario_start_url
                )
            except ValueError:
                initial_url = self.current_scenario_start_url
            self.ui.txt_start_url_override.setText(initial_url)
        self.ui.txt_start_url_override.setEnabled(True)
        self.update_effective_url_preview()

    # ------------------------------------------
    # 新規/編集モード切替と保存ロジック
    # ------------------------------------------
    def open_create_project_page(self):
        self.is_edit_mode = False
        self.ui.lbl_page_title.setText("新規プロジェクトを作成")
        self.ui.lbl_page_desc.setText("プロジェクト用のフォルダと基本設定ファイル（config.json）を作成します。")
        self.ui.btn_confirm_proj.setText("プロジェクトを作成")
        
        self.ui.input_proj_id.clear()
        self.ui.input_client.clear()
        self.ui.input_task.clear()
        self.ui.input_environments.clear()
        
        self.ui.tpl_frame.setVisible(False)
        self.ui.btn_delete_proj.setVisible(False)
        self.ui.stacked_widget.setCurrentIndex(1)

    def open_edit_project_page(self):
        current_proj = self.ui.combo_proj.currentText().strip()
        if not current_proj:
            QMessageBox.warning(self, "エラー", "編集対象のプロジェクトが選択されていません。")
            return

        self.is_edit_mode = True
        self.current_editing_proj = current_proj
        
        self.ui.lbl_page_title.setText("プロジェクト設定を編集")
        self.ui.lbl_page_desc.setText("選択中のプロジェクトIDと基本情報を編集します。")
        self.ui.btn_confirm_proj.setText("変更を保存")

        config_path = os.path.join("project", current_proj, "config.json")
        client_name = ""
        task_name = ""
        environments = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    client_name = cfg.get("client_name", "")
                    task_name = cfg.get("task_name", "")
                    environments = cfg.get("environments", {})
            except Exception as e:
                self.log_write(f"config.json 読み込み警告: {str(e)}\n")

        self.ui.input_proj_id.setText(current_proj)
        self.ui.input_client.setText(client_name)
        self.ui.input_task.setText(task_name)
        self.ui.input_environments.setPlainText(environment_lines(environments))
        
        self.ui.tpl_frame.setVisible(True)
        self.ui.btn_delete_proj.setVisible(True)
        self.ui.stacked_widget.setCurrentIndex(1)
        self.log_write(f"プロジェクト設定の編集画面を開きました: {current_proj}\n", project_name=current_proj)

    def delete_project_action(self):
        project_name = self.current_editing_proj.strip()
        if not self.is_edit_mode or not project_name:
            QMessageBox.warning(self, "削除エラー", "削除対象のプロジェクトが選択されていません。")
            return

        try:
            project_dir = resolve_project_directory(project_name)
        except ValueError as error:
            QMessageBox.critical(self, "削除エラー", str(error))
            return

        if not os.path.isdir(project_dir):
            QMessageBox.warning(self, "削除エラー", f"プロジェクトフォルダが見つかりません:\n{project_dir}")
            return

        answer = QMessageBox.question(
            self,
            "プロジェクトの削除",
            f"プロジェクト『{project_name}』を削除しますか？\n"
            "シナリオ、計測データ、Excelファイルもすべて対象です。",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if answer != QMessageBox.Yes:
            return

        delete_log = f"プロジェクトの削除処理を開始しました: {project_name}\n"
        self.log_write(delete_log, project_name=project_name)
        moved, _ = normalize_trash_result(QFile.moveToTrash(project_dir))
        if not moved:
            self.log_write(f"プロジェクトの削除に失敗しました: {project_name}\n", project_name=project_name)
            QMessageBox.critical(self, "削除エラー", "プロジェクトを削除できませんでした。")
            return

        self.log_write(f"プロジェクトを削除しました: {project_name}\n", persist=False)
        self.current_editing_proj = ""
        self.is_edit_mode = False
        self.refresh_project_list()
        self.ui.stacked_widget.setCurrentIndex(0)
        QMessageBox.information(self, "削除完了", f"プロジェクト『{project_name}』を削除しました。")

    def save_project_action(self):
        proj_id = self.ui.input_proj_id.text().strip()
        client = self.ui.input_client.text().strip() or "クライアント名未設定"
        task = self.ui.input_task.text().strip() or "課題名未設定"

        if not proj_id:
            QMessageBox.warning(self, "入力エラー", "プロジェクトIDを入力してください。")
            return

        try:
            environments = parse_environment_lines(self.ui.input_environments.toPlainText())
        except ValueError as error:
            QMessageBox.warning(self, "実行環境の入力エラー", str(error))
            return

        if self.is_edit_mode:
            # 編集モード
            old_proj_id = self.current_editing_proj
            old_dir = os.path.join("project", old_proj_id)
            new_dir = os.path.join("project", proj_id)

            if proj_id != old_proj_id:
                if os.path.exists(new_dir):
                    QMessageBox.warning(self, "エラー", f"既に '{proj_id}' というフォルダ名が存在します。別の名前を指定してください。")
                    return
                try:
                    os.rename(old_dir, new_dir)
                except Exception as e:
                    QMessageBox.critical(self, "リネームエラー", f"フォルダ名の変更に失敗しました:\n{str(e)}")
                    return

            target_dir = new_dir if proj_id != old_proj_id else old_dir
            config_path = os.path.join(target_dir, "config.json")
            config_data = {}
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        config_data = json.load(f)
                except Exception:
                    config_data = {}

            before_settings = format_project_settings(old_proj_id, config_data)
            config_data["client_name"] = client
            config_data["task_name"] = task
            config_data["environments"] = environments
            after_settings = format_project_settings(proj_id, config_data)

            try:
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(config_data, f, indent=4, ensure_ascii=False)
            except Exception as e:
                QMessageBox.critical(self, "保存エラー", f"config.json の保存に失敗しました:\n{str(e)}")
                return
            
            self.refresh_project_list()
            idx = self.ui.combo_proj.findText(proj_id)
            if idx >= 0: self.ui.combo_proj.setCurrentIndex(idx)
            update_target = f"{old_proj_id} -> {proj_id}" if proj_id != old_proj_id else proj_id
            self.log_write(
                f"プロジェクト設定を更新しました: {update_target}\n"
                f"変更前:\n{before_settings}\n"
                f"変更後:\n{after_settings}\n",
                project_name=proj_id,
            )
            QMessageBox.information(self, "保存完了", f"プロジェクト '{proj_id}' の設定を更新しました！")

        else:
            # 新規作成モード
            proj_dir = os.path.join("project", proj_id)
            if os.path.exists(proj_dir):
                QMessageBox.warning(self, "エラー", f"既に '{proj_id}' というプロジェクトが存在します。")
                return

            config_data = {
                "client_name": client,
                "task_name": task,
                "environments": environments,
                "excel_setting": {
                    "font_name": "游ゴシック", "theme_color_new": "E2EFDA", "theme_color_old": "FFF2CC", "diff_color": "FFC7CE", "diff_font_color": "9C0006"
                },
                "extraction_rules": {
                    "ignore_params": ["_ts", "gtm_auth", "gjid", "gtm", "requestId", "configId"], "nested_separator": "."
                }
            }
            try:
                ensure_project_directories(proj_dir)
                copy_default_template(proj_dir)
                with open(os.path.join(proj_dir, "config.json"), "w", encoding="utf-8") as f:
                    json.dump(config_data, f, indent=4, ensure_ascii=False)
            except (OSError, FileNotFoundError) as error:
                if os.path.isdir(proj_dir):
                    shutil.rmtree(proj_dir)
                QMessageBox.critical(self, "プロジェクト作成エラー", str(error))
                return

            self.refresh_project_list()
            idx = self.ui.combo_proj.findText(proj_id)
            if idx >= 0: self.ui.combo_proj.setCurrentIndex(idx)
            self.log_write(
                f"プロジェクトを作成しました: {proj_id}\n"
                f"設定情報:\n{format_project_settings(proj_id, config_data)}\n",
                project_name=proj_id,
            )
            QMessageBox.information(self, "成功", f"プロジェクト '{proj_id}' を作成しました！")

        self.ui.stacked_widget.setCurrentIndex(0)

    def open_template_excel(self):
        target_proj = self.ui.input_proj_id.text().strip() or self.current_editing_proj
        template_path = os.path.abspath(os.path.join("project", target_proj, "template.xlsx"))

        if os.path.exists(template_path):
            try:
                if sys.platform == "win32":
                    os.startfile(template_path)
                elif sys.platform == "darwin":
                    subprocess.call(["open", template_path])
                else:
                    subprocess.call(["xdg-open", template_path])
                self.log_write(f"テンプレートファイルを開きました: {template_path}\n")
            except Exception as e:
                QMessageBox.critical(self, "実行エラー", f"ファイルを開く際にエラーが発生しました:\n{str(e)}")
        else:
            QMessageBox.information(
                self, 
                "ファイル未配置", 
                f"現在 '{target_proj}' には個別の template.xlsx が配置されていません。\n\n"
                f"配置先パス:\n{template_path}\n\n"
                "ここにカスタムデザインの template.xlsx を配置すると、突合比較時に優先して読み込まれます。"
            )

    def log_write(self, msg, project_name=None, persist=True):
        self.ui.txt_log.moveCursor(QTextCursor.End)
        self.ui.txt_log.insertPlainText(msg)
        self.ui.txt_log.verticalScrollBar().setValue(self.ui.txt_log.verticalScrollBar().maximum())
        if not persist:
            return
        target_project = project_name or self.ui.combo_proj.currentText().strip()
        try:
            append_project_log(target_project, msg)
        except (OSError, ValueError):
            pass

    def select_file(self, target_lineedit):
        proj = self.ui.combo_proj.currentText()
        other_lineedit = self.ui.txt_f2 if target_lineedit is self.ui.txt_f1 else self.ui.txt_f1
        other_path = other_lineedit.text().strip().strip("'").strip('"')
        project_scenarios = os.path.abspath(os.path.join("project", proj, "scenario"))
        if other_path and os.path.isfile(other_path):
            init_dir = os.path.dirname(os.path.abspath(other_path))
        elif os.path.isdir(project_scenarios):
            init_dir = project_scenarios
        else:
            init_dir = os.getcwd()
        path, _ = QFileDialog.getOpenFileName(self, "JSONファイルを選択", init_dir, "JSON Files (*.json)")
        if path: target_lineedit.setText(path)

    def update_comparison_output_name(self, *_):
        latest_path = self.ui.txt_f1.text().strip().strip("'").strip('"')
        base_path = self.ui.txt_f2.text().strip().strip("'").strip('"')
        if not latest_path or not base_path:
            self.ui.txt_out.setText("result.xlsx")
            return
        generated_name = comparison_output_filename(latest_path, base_path)
        if generated_name:
            self.ui.txt_out.setText(generated_name)

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
        self.log_write(f"[{datetime.now().strftime('%H:%M:%S')}] 比較レポートの生成を開始します。\n")

        self.analysis_worker = ReporterWorker(proj, f1, f2, out, self.sig_log, self.sig_finish, self.sig_err)
        self.analysis_worker.start()

    def on_analysis_finished(self, result_path):
        self.ui.btn_run_analysis.setEnabled(True)
        self.ui.progress.setVisible(False)
        self.log_write("すべての処理が正常に完了しました。\n")
        if result_path and os.path.exists(result_path):
            if sys.platform == "win32": os.startfile(result_path)
            elif sys.platform == "darwin": subprocess.call(["open", result_path])

    def on_analysis_error(self, err_msg):
        self.ui.btn_run_analysis.setEnabled(True)
        self.ui.progress.setVisible(False)
        self.log_write(f"エラーが発生しました:\n{err_msg}\n")
        QMessageBox.critical(self, "エラー", f"エラーが発生しました:\n{err_msg}")

    # --- シナリオ実行処理 ---
    def start_scenario_execution(self):
        proj = self.ui.combo_proj.currentText()
        scenario_file = self.ui.combo_scenario.currentText()
        
        if not scenario_file or scenario_file.startswith("※"):
            QMessageBox.warning(self, "エラー", "実行可能なシナリオが選択されていません。")
            return

        try:
            execution_url = self.selected_execution_url()
        except ValueError as error:
            QMessageBox.warning(self, "開始URLの入力エラー", str(error))
            return

        environment = self.ui.combo_environment.currentText() if self.ui.combo_environment.currentData() else None
        device_id = self.ui.combo_device.currentData()
        try:
            if device_id is None:
                raise ValueError("global_config.jsonのデバイス設定を確認し、アプリを再起動してください。")
            execution_device = resolve_device(device_id)
        except ValueError as error:
            QMessageBox.warning(self, "デバイス設定エラー", str(error))
            return
        start_url_override = (
            self.ui.txt_start_url_override.text().strip()
            if self.ui.chk_override_start_url.isChecked() else None
        )
            
        self.ui.btn_exec_scenario.setEnabled(False)
        self.ui.txt_log.clear()
        
        headless_mode = self.ui.chk_headless.isChecked()
        mode_str = "【ヘッドレスモード】" if headless_mode else "【通常モード (画面表示)】"
        
        self.log_write(f"[{datetime.now().strftime('%H:%M:%S')}] シナリオ実行を開始します: {scenario_file} {mode_str}\n")
        if environment:
            self.log_write(f"実行環境: {environment}\n")
        if start_url_override:
            self.log_write("開始URLは今回の実行だけ変更します。\n")
        self.log_write(f"実行URL: {execution_url}\n")
        self.log_write(f"実行デバイス: {execution_device['name']}\n")
        self.log_write("==================================================\n")
        
        self.scenario_worker = ScenarioWorker(
            proj,
            scenario_file,
            headless_mode,
            environment=environment,
            start_url_override=start_url_override,
            device=device_id,
        )
        self.scenario_worker.log.connect(self.log_write)
        self.scenario_worker.finished.connect(self.on_scenario_finished)
        self.scenario_worker.start()
        
    def on_scenario_finished(self, success):
        self.ui.btn_exec_scenario.setEnabled(True)
        self.log_write("==================================================\n")
        if success:
            self.log_write("シナリオの実行が完了しました。計測データはscenario配下のシナリオ別フォルダに保存されています。\n")
        else:
            self.log_write("シナリオの実行に失敗しました。計測結果は保存されていません。\n")
            QMessageBox.warning(
                self,
                "シナリオ実行エラー",
                "シナリオを最後まで実行できませんでした。処理ログを確認してください。",
            )

    # --- 自動シナリオレコーダー処理 ---
    def start_auto_record(self):
        proj = self.ui.combo_proj.currentText()
        filename = self.ui.txt_scenario_file_auto.text().strip()
        url = self.ui.txt_url_auto.text().strip()
        memo = self.ui.txt_memo_auto.text().strip() # メモフィールドを取得
        
        if not proj:
            QMessageBox.warning(self, "エラー", "対象プロジェクトが選択されていません。")
            return
        if not filename:
            QMessageBox.warning(self, "エラー", "保存するシナリオファイル名を入力してください。")
            return
        if not url:
            QMessageBox.warning(self, "エラー", "開始URLを入力してください。")
            return
        if self.recording_settings_error:
            QMessageBox.warning(self, "記録サイズの設定エラー", self.recording_settings_error)
            return
        viewport = validate_recording_viewport({
            'width': self.ui.spin_record_width.value(),
            'height': self.ui.spin_record_height.value(),
        })
            
        if not filename.endswith(".json"):
            filename += ".json"

        scenario_name = safe_file_component(scenario_name_from_reference(filename))
            
        self.ui.btn_record_auto.setEnabled(False)
        self.ui.txt_log.clear()
        self.log_write(f"[{datetime.now().strftime('%H:%M:%S')}] 操作レコーダーを起動します。\n")
        self.log_write(f"開始URL: {url}\n")
        self.log_write(f"記録時の表示領域: {viewport['width']} × {viewport['height']} px\n")
        self.log_write(f"保存先: project/{proj}/scenario/{scenario_name}/{scenario_name}.json\n")
        if memo: self.log_write(f"メモ: {memo}\n")
        self.log_write("==================================================\n")
        self.log_write("起動したブラウザで操作を行い、終わったらブラウザを閉じてください。\n")
        
        # 引数にmemoを追加してワーカーを起動
        self.record_worker = AutoRecordWorker(proj, filename, url, memo, viewport=viewport)
        self.record_worker.log.connect(self.log_write)
        self.record_worker.finished.connect(lambda s, p=proj: self.on_record_finished(s, p))
        self.record_worker.start()
        
    def on_record_finished(self, success, proj):
        self.ui.btn_record_auto.setEnabled(True)
        self.log_write("==================================================\n")
        if success:
            self.log_write("シナリオを保存しました。「シナリオ実行」タブから確認できます。\n")
            self.update_scenario_list(proj)
        else:
            self.log_write("レコーダーが終了しましたが、エラーが発生した可能性があります。\n")

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
