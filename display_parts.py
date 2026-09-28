from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QComboBox, QTextEdit, QProgressBar,
                               QTabWidget, QStackedWidget, QFormLayout, QGridLayout,
                               QFrame, QCheckBox, QSizePolicy, QStyle, QStyleOptionButton)
from PySide6.QtCore import Qt
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QFontDatabase, QPainter, QPen

# ==========================================
# カスタムUI部品
# ==========================================

class DragDropLineEdit(QLineEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setProperty("dragOver", True)
            self.style().unpolish(self)
            self.style().polish(self)

    def dragLeaveEvent(self, event):
        self.setProperty("dragOver", False)
        self.style().unpolish(self)
        self.style().polish(self)

    def dropEvent(self, event):
        self.setProperty("dragOver", False)
        self.style().unpolish(self)
        self.style().polish(self)
        urls = event.mimeData().urls()
        if urls:
            self.setText(urls[0].toLocalFile())


class ArrowComboBox(QComboBox):
    """Combo box with a theme-independent visible chevron."""

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor("#475467"), 2)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)

        center_x = self.width() - 16
        center_y = self.height() / 2
        painter.drawLine(QPointF(center_x - 4, center_y - 2), QPointF(center_x, center_y + 2))
        painter.drawLine(QPointF(center_x, center_y + 2), QPointF(center_x + 4, center_y - 2))


class CheckMarkBox(QCheckBox):
    """Checkbox that keeps a visible check mark with the custom theme."""

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.isChecked():
            return

        option = QStyleOptionButton()
        self.initStyleOption(option)
        indicator = self.style().subElementRect(QStyle.SE_CheckBoxIndicator, option, self)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor("#FFFFFF"), 2)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)

        left = indicator.left()
        top = indicator.top()
        painter.drawLine(QPointF(left + 4, top + 9), QPointF(left + 7, top + 12))
        painter.drawLine(QPointF(left + 7, top + 12), QPointF(left + 13, top + 5))


# ==========================================
# UIレイアウト構築クラス
# ==========================================

class Ui_MainWindow:
    def setupUi(self, main_window):
        main_window.setWindowTitle("AutoEventTracker")
        main_window.setMinimumSize(1100, 720)
        main_window.resize(1280, 800)

        self.stacked_widget = QStackedWidget()
        main_window.setCentralWidget(self.stacked_widget)

        self._setup_main_page()
        self._setup_create_project_page()

        self.stacked_widget.setCurrentIndex(0)

    # ------------------------------------------
    # メイン画面 (ページ 0)
    # ------------------------------------------
    def _setup_main_page(self):
        main_widget = QWidget()
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)

        # ヘッダー
        header_layout = QHBoxLayout()
        header_layout.setSpacing(16)

        header_text = QVBoxLayout()
        header_text.setSpacing(2)

        title = QLabel("AutoEventTracker")
        title.setObjectName("mainTitle")
        header_text.addWidget(title)

        header_layout.addLayout(header_text)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # プロジェクト選択バー
        project_bar = QFrame()
        project_bar.setObjectName("projectBar")
        proj_layout = QHBoxLayout(project_bar)
        proj_layout.setContentsMargins(16, 12, 16, 12)
        proj_layout.setSpacing(12)
        
        lbl_proj = QLabel("対象プロジェクト:")
        lbl_proj.setProperty("class", "bold-label")
        proj_layout.addWidget(lbl_proj)

        self.combo_proj = ArrowComboBox()
        self.combo_proj.setObjectName("projectCombo")
        proj_layout.addWidget(self.combo_proj)

        self.btn_edit_proj = QPushButton("プロジェクト設定編集")
        self.btn_edit_proj.setObjectName("secondaryBtn")
        self.btn_edit_proj.setCursor(Qt.PointingHandCursor)
        proj_layout.addWidget(self.btn_edit_proj)

        self.btn_create_proj = QPushButton("新規プロジェクト")
        self.btn_create_proj.setObjectName("successBtn")
        self.btn_create_proj.setCursor(Qt.PointingHandCursor)
        proj_layout.addWidget(self.btn_create_proj)
        layout.addWidget(project_bar)

        # 操作画面と処理ログを左右に配置
        workspace_layout = QHBoxLayout()
        workspace_layout.setSpacing(18)

        operation_panel = QWidget()
        operation_layout = QVBoxLayout(operation_panel)
        operation_layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("workspaceTabs")
        self.tabs.setDocumentMode(True)
        self.tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.tabs.addTab(self._create_analysis_tab(), "計測データ比較")
        self.tabs.addTab(self._create_execution_tab(), "シナリオ実行")
        self.tabs.addTab(self._create_scenario_tab(), "シナリオ作成")
        operation_layout.addWidget(self.tabs)
        operation_layout.addStretch(1)
        workspace_layout.addWidget(operation_panel, stretch=1)

        log_panel = QWidget()
        log_layout = QVBoxLayout(log_panel)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(10)

        lbl_log = QLabel("処理ログ")
        lbl_log.setObjectName("logTitle")
        log_layout.addWidget(lbl_log)

        self.txt_log = QTextEdit()
        self.txt_log.setObjectName("logConsole")
        self.txt_log.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.txt_log.setReadOnly(True)
        log_layout.addWidget(self.txt_log, stretch=1)
        workspace_layout.addWidget(log_panel, stretch=1)

        layout.addLayout(workspace_layout, stretch=1)

        self.stacked_widget.addWidget(main_widget)

    # --- 分析タブ ---
    def _create_analysis_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(26)
        layout.setContentsMargins(20, 28, 20, 28)

        file1_group = QVBoxLayout()
        file1_group.setSpacing(7)
        lbl_f1 = QLabel("最新の計測データ")
        lbl_f1.setProperty("class", "bold-label")
        file1_group.addWidget(lbl_f1)

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        self.txt_f1 = DragDropLineEdit()
        self.txt_f1.setPlaceholderText("ファイルをドラッグ＆ドロップ...")
        self.btn_f1 = QPushButton("選択")
        self.btn_f1.setObjectName("secondaryBtn")
        row1.addWidget(self.txt_f1)
        row1.addWidget(self.btn_f1)
        file1_group.addLayout(row1)
        layout.addLayout(file1_group)

        file2_group = QVBoxLayout()
        file2_group.setSpacing(7)
        lbl_f2 = QLabel("比較元の計測データ")
        lbl_f2.setProperty("class", "bold-label")
        file2_group.addWidget(lbl_f2)

        row2 = QHBoxLayout()
        row2.setSpacing(10)
        self.txt_f2 = DragDropLineEdit()
        self.txt_f2.setPlaceholderText("ファイルをドラッグ＆ドロップ...")
        self.btn_f2 = QPushButton("選択")
        self.btn_f2.setObjectName("secondaryBtn")
        row2.addWidget(self.txt_f2)
        row2.addWidget(self.btn_f2)
        file2_group.addLayout(row2)
        layout.addLayout(file2_group)

        output_group = QVBoxLayout()
        output_group.setSpacing(7)
        lbl_out = QLabel("出力するExcelファイル名:")
        lbl_out.setProperty("class", "bold-label")
        output_group.addWidget(lbl_out)

        self.txt_out = QLineEdit("result.xlsx")
        output_group.addWidget(self.txt_out)
        layout.addLayout(output_group)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)
        layout.addStretch(1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        self.btn_run_analysis = QPushButton("比較レポートを生成")
        self.btn_run_analysis.setObjectName("actionBtn")
        self.btn_run_analysis.setCursor(Qt.PointingHandCursor)
        
        self.btn_open = QPushButton("出力フォルダを開く")
        self.btn_open.setObjectName("secondaryActionBtn")
        self.btn_open.setCursor(Qt.PointingHandCursor)

        btn_row.addWidget(self.btn_run_analysis, stretch=3, alignment=Qt.AlignBottom)
        btn_row.addWidget(self.btn_open, stretch=1, alignment=Qt.AlignBottom)
        layout.addLayout(btn_row)

        return tab

    # --- シナリオ実行タブ ---
    def _create_execution_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 28, 20, 28)
        layout.setSpacing(24)

        scenario_group = QVBoxLayout()
        scenario_group.setSpacing(7)
        lbl_exec = QLabel("実行するシナリオ:")
        lbl_exec.setProperty("class", "bold-label")
        scenario_group.addWidget(lbl_exec)

        exec_header = QHBoxLayout()
        exec_header.setSpacing(16)
        self.combo_scenario = ArrowComboBox()
        self.combo_scenario.setObjectName("scenarioCombo")
        exec_header.addWidget(self.combo_scenario, stretch=2)

        self.chk_headless = CheckMarkBox("ブラウザを表示せずに実行")
        exec_header.addWidget(self.chk_headless, stretch=1)
        scenario_group.addLayout(exec_header)
        layout.addLayout(scenario_group)

        environment_group = QVBoxLayout()
        environment_group.setSpacing(7)
        lbl_environment = QLabel("実行環境:")
        lbl_environment.setProperty("class", "bold-label")
        self.combo_environment = QComboBox()
        self.combo_environment.setToolTip("プロジェクト設定に登録した環境を選択します。")
        environment_group.addWidget(lbl_environment)
        environment_group.addWidget(self.combo_environment)
        layout.addLayout(environment_group)

        override_layout = QVBoxLayout()
        override_layout.setSpacing(8)
        self.chk_override_start_url = CheckMarkBox("今回だけ開始URLを変更")
        self.txt_start_url_override = QLineEdit()
        self.txt_start_url_override.setObjectName("startUrlOverrideInput")
        self.txt_start_url_override.setPlaceholderText("例: https://test01.example.com/path/")
        self.txt_start_url_override.setEnabled(False)
        override_layout.addWidget(self.chk_override_start_url)
        override_layout.addWidget(self.txt_start_url_override)
        layout.addLayout(override_layout)

        # 情報カード：右端ギリギリまで広がり、文字の下部が切れないレイアウト
        self.info_frame = QFrame()
        self.info_frame.setObjectName("infoFrame")
        self.info_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        
        info_layout = QGridLayout(self.info_frame)
        info_layout.setContentsMargins(20, 18, 20, 18)
        info_layout.setHorizontalSpacing(16)
        info_layout.setVerticalSpacing(16)
        
        # ラベル列の幅を固定し、右側の値列をカード右端までストレッチ
        info_layout.setColumnStretch(0, 0)
        info_layout.setColumnStretch(1, 1)

        lbl_i1 = QLabel("シナリオ名:")
        lbl_i1.setProperty("class", "bold-label")
        lbl_i1.setFixedWidth(130)

        lbl_i2 = QLabel("開始URL:")
        lbl_i2.setProperty("class", "bold-label")
        lbl_i2.setFixedWidth(130)

        lbl_i3 = QLabel("概要:")
        lbl_i3.setProperty("class", "bold-label")
        lbl_i3.setFixedWidth(130)

        lbl_i4 = QLabel("今回の実行URL:")
        lbl_i4.setProperty("class", "bold-label")
        lbl_i4.setFixedWidth(130)

        # 値ラベル：セル幅いっぱいに引き伸ばす（alignment 引数を外す）
        self.lbl_info_name = QLabel("-")
        self.lbl_info_name.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        
        self.lbl_info_url = QLabel("-")
        self.lbl_info_url.setObjectName("infoUrlLabel")
        self.lbl_info_url.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.lbl_info_url.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_info_url.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        
        self.lbl_info_memo = QLabel("-")
        self.lbl_info_memo.setObjectName("infoMemoLabel")
        self.lbl_info_memo.setWordWrap(True)
        self.lbl_info_memo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.lbl_info_effective_url = QLabel("-")
        self.lbl_info_effective_url.setObjectName("infoUrlLabel")
        self.lbl_info_effective_url.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.lbl_info_effective_url.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_info_effective_url.setWordWrap(True)
        self.lbl_info_effective_url.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # グリッドへ配置（右側ラベルは横幅いっぱいに拡張）
        info_layout.addWidget(lbl_i1, 0, 0, Qt.AlignTop)
        info_layout.addWidget(self.lbl_info_name, 0, 1)

        info_layout.addWidget(lbl_i2, 1, 0, Qt.AlignTop)
        info_layout.addWidget(self.lbl_info_url, 1, 1)

        info_layout.addWidget(lbl_i4, 2, 0, Qt.AlignTop)
        info_layout.addWidget(self.lbl_info_effective_url, 2, 1)

        info_layout.addWidget(lbl_i3, 3, 0, Qt.AlignTop)
        info_layout.addWidget(self.lbl_info_memo, 3, 1)

        layout.addWidget(self.info_frame)
        layout.addStretch(1)

        self.btn_exec_scenario = QPushButton("シナリオを実行")
        self.btn_exec_scenario.setObjectName("actionBtn")
        self.btn_exec_scenario.setCursor(Qt.PointingHandCursor)
        layout.addWidget(self.btn_exec_scenario)

        return tab

    # --- シナリオ作成タブ ---
    def _create_scenario_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 28, 20, 28)
        layout.setSpacing(28)

        file_group = QVBoxLayout()
        file_group.setSpacing(7)
        lbl_s1 = QLabel("① シナリオファイル名:")
        lbl_s1.setProperty("class", "bold-label")
        file_group.addWidget(lbl_s1)

        self.txt_scenario_file_auto = QLineEdit()
        self.txt_scenario_file_auto.setPlaceholderText("例: my_scenario.json")
        file_group.addWidget(self.txt_scenario_file_auto)
        layout.addLayout(file_group)

        url_group = QVBoxLayout()
        url_group.setSpacing(7)
        lbl_s2 = QLabel("② 記録を開始するURL:")
        lbl_s2.setProperty("class", "bold-label")
        url_group.addWidget(lbl_s2)

        self.txt_url_auto = QLineEdit()
        self.txt_url_auto.setPlaceholderText("例: https://shop.example.com/")
        url_group.addWidget(self.txt_url_auto)
        layout.addLayout(url_group)

        memo_group = QVBoxLayout()
        memo_group.setSpacing(7)
        lbl_s3 = QLabel("③ シナリオの概要（任意）:")
        lbl_s3.setProperty("class", "bold-label")
        memo_group.addWidget(lbl_s3)

        self.txt_memo_auto = QLineEdit()
        self.txt_memo_auto.setPlaceholderText("例: 新規会員登録から購入完了までの正常系フロー")
        memo_group.addWidget(self.txt_memo_auto)
        layout.addLayout(memo_group)

        layout.addStretch(1)
        self.btn_record_auto = QPushButton("ブラウザ操作の記録を開始")
        self.btn_record_auto.setObjectName("actionBtn")
        self.btn_record_auto.setCursor(Qt.PointingHandCursor)
        self.btn_record_auto.setToolTip(
            "ボタンを押すとブラウザが開きます。\n"
            "普段通りに画面を操作し、完了後にブラウザを閉じてください。\n"
            "操作内容がシナリオJSONとして自動保存されます。"
        )
        self.btn_record_auto.setToolTipDuration(12000)
        layout.addWidget(self.btn_record_auto)

        return tab

    # ------------------------------------------
    # プロジェクト作成・編集 兼用画面 (ページ 1)
    # ------------------------------------------
    def _setup_create_project_page(self):
        create_widget = QWidget()
        layout = QVBoxLayout(create_widget)
        layout.setContentsMargins(48, 48, 48, 48)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(16)

        self.lbl_page_title = QLabel("新規プロジェクトを作成")
        self.lbl_page_title.setObjectName("sectionTitle")
        layout.addWidget(self.lbl_page_title)
        
        self.lbl_page_desc = QLabel("プロジェクト用のフォルダと基本設定ファイル（config.json）を作成します。")
        self.lbl_page_desc.setObjectName("descLabel")
        layout.addWidget(self.lbl_page_desc)

        form_frame = QFrame()
        form_frame.setObjectName("formFrame")
        form_layout = QFormLayout(form_frame)
        form_layout.setContentsMargins(24, 24, 24, 24)
        form_layout.setSpacing(18)

        # ラベル側の幅を適切に確保し、入力フィールドが横に広がるように FieldGrowthPolicy を設定
        form_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.input_proj_id = QLineEdit()
        self.input_proj_id.setPlaceholderText("例: my_project_2026")
        # 横幅がいっぱいまで広がるようにポリシーを設定
        self.input_proj_id.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.input_client = QLineEdit()
        self.input_client.setPlaceholderText("例: 株式会社サンプル 様")
        self.input_client.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.input_task = QLineEdit()
        self.input_task.setPlaceholderText("例: カート追加イベントのパケット検証")
        self.input_task.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.input_environments = QTextEdit()
        self.input_environments.setPlaceholderText(
            "1行に1環境を「環境名 = ベースURL」で入力\n"
            "例: 本番 = https://www.example.com\n"
            "    ステージング = https://stg.example.com"
        )
        self.input_environments.setFixedHeight(100)
        self.input_environments.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        lbl_p1 = QLabel("プロジェクトID（半角英数字推奨）:")
        lbl_p1.setProperty("class", "bold-label")
        lbl_p2 = QLabel("クライアント名:")
        lbl_p2.setProperty("class", "bold-label")
        lbl_p3 = QLabel("検証タスク名:")
        lbl_p3.setProperty("class", "bold-label")
        lbl_p4 = QLabel("実行環境:")
        lbl_p4.setProperty("class", "bold-label")
        lbl_p4.setToolTip("シナリオ実行時に選べるサブドメインを登録します。")

        form_layout.addRow(lbl_p1, self.input_proj_id)
        form_layout.addRow(lbl_p2, self.input_client)
        form_layout.addRow(lbl_p3, self.input_task)
        form_layout.addRow(lbl_p4, self.input_environments)

        layout.addWidget(form_frame)

        # --- テンプレート操作枠 (編集時のみ表示させる用) ---
        self.tpl_frame = QFrame()
        self.tpl_frame.setObjectName("infoFrame")
        tpl_layout = QVBoxLayout(self.tpl_frame)
        tpl_layout.setContentsMargins(24, 20, 24, 20)
        
        tpl_title = QLabel("Excelテンプレートの設定")
        tpl_title.setProperty("class", "bold-label")
        tpl_layout.addWidget(tpl_title)

        tpl_desc = QLabel(
            "このプロジェクト独自の比較フォーマットを使用する場合、フォルダに template.xlsx を配置します。\n"
            "※ Excel内のセルに {{CLIENT_NAME}}, {{TASK_NAME}}, {{PROJECT_ID}}, {{RUN_DATE}} と書くと、レポート生成時に自動置換されます。"
        )
        tpl_desc.setObjectName("descLabel")
        tpl_layout.addWidget(tpl_desc)

        self.btn_open_template = QPushButton("template.xlsxを開く")
        self.btn_open_template.setObjectName("secondaryBtn")
        self.btn_open_template.setCursor(Qt.PointingHandCursor)
        tpl_layout.addWidget(self.btn_open_template, 0, Qt.AlignLeft)
        
        self.tpl_frame.setVisible(False) # 初期は非表示
        layout.addWidget(self.tpl_frame)

        # --- ボタン ---
        layout.addSpacing(16)

        delete_layout = QHBoxLayout()
        self.btn_delete_proj = QPushButton("プロジェクトを削除")
        self.btn_delete_proj.setObjectName("dangerBtn")
        self.btn_delete_proj.setCursor(Qt.PointingHandCursor)
        self.btn_delete_proj.setVisible(False)
        delete_layout.addWidget(self.btn_delete_proj)
        delete_layout.addStretch(1)
        layout.addLayout(delete_layout)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        
        self.btn_cancel_proj = QPushButton("キャンセル")
        self.btn_cancel_proj.setObjectName("secondaryBtn")
        self.btn_cancel_proj.setCursor(Qt.PointingHandCursor)
        
        self.btn_confirm_proj = QPushButton("プロジェクトを作成")
        self.btn_confirm_proj.setObjectName("primaryBtn")
        self.btn_confirm_proj.setCursor(Qt.PointingHandCursor)

        btn_layout.addStretch(1)
        btn_layout.addWidget(self.btn_cancel_proj, stretch=1)
        btn_layout.addWidget(self.btn_confirm_proj, stretch=1)
        btn_layout.addStretch(1)
        layout.addLayout(btn_layout)

        self.stacked_widget.addWidget(create_widget)
