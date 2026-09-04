from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QComboBox, QTextEdit, QProgressBar,
                               QTabWidget, QStackedWidget, QFormLayout, QFrame, QCheckBox)
from PySide6.QtCore import Qt

# ==========================================
# 🎨 カスタムUI部品
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


# ==========================================
# 📐 UIレイアウト構築クラス
# ==========================================

class Ui_MainWindow:
    def setupUi(self, main_window):
        main_window.setWindowTitle("AutoEventTracker - 統合テストスイート")
        main_window.setFixedSize(840, 820)

        self.stacked_widget = QStackedWidget()
        main_window.setCentralWidget(self.stacked_widget)

        self._setup_main_page()
        self._setup_create_project_page()

        self.stacked_widget.setCurrentIndex(0)

    # ------------------------------------------
    # 🏠 メイン画面 (ページ 0)
    # ------------------------------------------
    def _setup_main_page(self):
        main_widget = QWidget()
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        # ヘッダー
        header_layout = QHBoxLayout()
        title = QLabel("AutoEventTracker")
        title.setObjectName("mainTitle")
        header_layout.addWidget(title)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # プロジェクト選択バー
        proj_layout = QHBoxLayout()
        proj_layout.setSpacing(12)
        
        lbl_proj = QLabel("📂 対象プロジェクト:")
        lbl_proj.setProperty("class", "bold-label")
        proj_layout.addWidget(lbl_proj)

        self.combo_proj = QComboBox()
        proj_layout.addWidget(self.combo_proj)

        self.btn_create_proj = QPushButton("＋ プロジェクト新規作成")
        self.btn_create_proj.setObjectName("successBtn")
        self.btn_create_proj.setCursor(Qt.PointingHandCursor)
        proj_layout.addWidget(self.btn_create_proj)
        proj_layout.addStretch()
        
        layout.addLayout(proj_layout)

        # タブエリア
        self.tabs = QTabWidget()
        self.tabs.addTab(self._create_analysis_tab(), "📊 分析 (パケット突合)")
        self.tabs.addTab(self._create_execution_tab(), "🚀 シナリオ実行")
        self.tabs.addTab(self._create_scenario_tab(), "🎬 シナリオ作成")
        layout.addWidget(self.tabs)

        # 処理ログ
        lbl_log = QLabel("📝 処理ログ")
        lbl_log.setProperty("class", "bold-label")
        layout.addWidget(lbl_log)

        self.txt_log = QTextEdit()
        self.txt_log.setObjectName("logConsole")
        self.txt_log.setReadOnly(True)
        layout.addWidget(self.txt_log, stretch=1)

        self.stacked_widget.addWidget(main_widget)

    # --- 📊 分析タブ ---
    def _create_analysis_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 24, 20, 20)

        lbl_f1 = QLabel("【現在データ / 新】 (JSONをドロップ or 選択):")
        lbl_f1.setProperty("class", "bold-label")
        layout.addWidget(lbl_f1)

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        self.txt_f1 = DragDropLineEdit()
        self.txt_f1.setPlaceholderText("ファイルをドラッグ＆ドロップ...")
        self.btn_f1 = QPushButton("📂 選択")
        self.btn_f1.setObjectName("secondaryBtn")
        row1.addWidget(self.txt_f1)
        row1.addWidget(self.btn_f1)
        layout.addLayout(row1)

        lbl_f2 = QLabel("【過去データ / 旧】 (JSONをドロップ or 選択):")
        lbl_f2.setProperty("class", "bold-label")
        layout.addWidget(lbl_f2)

        row2 = QHBoxLayout()
        row2.setSpacing(10)
        self.txt_f2 = DragDropLineEdit()
        self.txt_f2.setPlaceholderText("ファイルをドラッグ＆ドロップ...")
        self.btn_f2 = QPushButton("📂 選択")
        self.btn_f2.setObjectName("secondaryBtn")
        row2.addWidget(self.txt_f2)
        row2.addWidget(self.btn_f2)
        layout.addLayout(row2)

        lbl_out = QLabel("成果物 Excel ファイル名:")
        lbl_out.setProperty("class", "bold-label")
        layout.addWidget(lbl_out)

        self.txt_out = QLineEdit("result.xlsx")
        layout.addWidget(self.txt_out)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        self.btn_run_analysis = QPushButton("🔥 比較レポートを自動生成する")
        self.btn_run_analysis.setObjectName("primaryBtn")
        self.btn_run_analysis.setCursor(Qt.PointingHandCursor)
        
        self.btn_open = QPushButton("📂 出力フォルダを開く")
        self.btn_open.setObjectName("secondaryBtn")
        self.btn_open.setCursor(Qt.PointingHandCursor)

        btn_row.addWidget(self.btn_run_analysis, stretch=3)
        btn_row.addWidget(self.btn_open, stretch=1)
        layout.addLayout(btn_row)
        layout.addStretch()

        return tab

    # --- 🚀 シナリオ実行タブ ---
    def _create_execution_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setAlignment(Qt.AlignTop)
        layout.setContentsMargins(20, 24, 20, 20)
        layout.setSpacing(16)

        lbl_exec = QLabel("実行するシナリオを選択してください:")
        lbl_exec.setProperty("class", "bold-label")
        layout.addWidget(lbl_exec)

        exec_header = QHBoxLayout()
        exec_header.setSpacing(16)
        self.combo_scenario = QComboBox()
        exec_header.addWidget(self.combo_scenario, stretch=2)

        self.chk_headless = QCheckBox("ヘッドレス実行 (ブラウザ画面を非表示)")
        exec_header.addWidget(self.chk_headless, stretch=1)
        layout.addLayout(exec_header)

        self.info_frame = QFrame()
        self.info_frame.setObjectName("infoFrame")
        info_layout = QFormLayout(self.info_frame)
        info_layout.setContentsMargins(18, 18, 18, 18)
        info_layout.setSpacing(12)

        self.lbl_info_name = QLabel("-")
        self.lbl_info_url = QLabel("-")
        self.lbl_info_url.setObjectName("infoUrlLabel")
        self.lbl_info_memo = QLabel("-")
        self.lbl_info_memo.setWordWrap(True)

        lbl_i1 = QLabel("📝 シナリオ名 (ID):")
        lbl_i1.setProperty("class", "bold-label")
        lbl_i2 = QLabel("🔗 開始 URL:")
        lbl_i2.setProperty("class", "bold-label")
        lbl_i3 = QLabel("💬 メモ / 概要:")
        lbl_i3.setProperty("class", "bold-label")

        info_layout.addRow(lbl_i1, self.lbl_info_name)
        info_layout.addRow(lbl_i2, self.lbl_info_url)
        info_layout.addRow(lbl_i3, self.lbl_info_memo)

        layout.addWidget(self.info_frame)

        self.btn_exec_scenario = QPushButton("▶️ Playwrightでシナリオを実行")
        self.btn_exec_scenario.setObjectName("actionBtn")
        self.btn_exec_scenario.setCursor(Qt.PointingHandCursor)
        layout.addWidget(self.btn_exec_scenario)

        return tab

    # --- 🎬 シナリオ作成タブ ---
    def _create_scenario_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setAlignment(Qt.AlignTop)
        layout.setContentsMargins(20, 24, 20, 20)
        layout.setSpacing(14)

        lbl_s1 = QLabel("① 保存するシナリオファイル名:")
        lbl_s1.setProperty("class", "bold-label")
        layout.addWidget(lbl_s1)

        self.txt_scenario_file_auto = QLineEdit()
        self.txt_scenario_file_auto.setPlaceholderText("例: my_scenario.json")
        layout.addWidget(self.txt_scenario_file_auto)

        lbl_s2 = QLabel("② 開始URL (このURLから自動記録ブラウザを立ち上げます):")
        lbl_s2.setProperty("class", "bold-label")
        layout.addWidget(lbl_s2)

        self.txt_url_auto = QLineEdit("https://www.sonysonpo.co.jp/")
        layout.addWidget(self.txt_url_auto)

        layout.addSpacing(6)
        self.btn_record_auto = QPushButton("⏺️ 記録開始 (ブラウザを操作して閉じるだけで自動保存)")
        self.btn_record_auto.setObjectName("dangerBtn")
        self.btn_record_auto.setCursor(Qt.PointingHandCursor)
        layout.addWidget(self.btn_record_auto)

        desc = QLabel(
            "💡 ヒント:\n"
            "・ボタンを押すとブラウザが開きます。普段通りに画面を操作してください。\n"
            "・操作が終わったら、ブラウザの「×」ボタンで閉じるだけでシナリオJSONが自動生成されます。\n"
            "・コードのコピペや要素セレクタの手動変換は不要です。"
        )
        desc.setObjectName("descLabel")
        layout.addWidget(desc)

        return tab

    # ------------------------------------------
    # ✨ プロジェクト作成画面 (ページ 1)
    # ------------------------------------------
    def _setup_create_project_page(self):
        create_widget = QWidget()
        layout = QVBoxLayout(create_widget)
        layout.setContentsMargins(48, 48, 48, 48)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(16)

        title = QLabel("✨ 新規プロジェクトを作成")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        
        desc = QLabel("案件用のフォルダ構成と基本設定ファイル（config.json）を自動生成します。")
        desc.setObjectName("descLabel")
        layout.addWidget(desc)

        form_frame = QFrame()
        form_frame.setObjectName("formFrame")
        form_layout = QFormLayout(form_frame)
        form_layout.setContentsMargins(24, 24, 24, 24)
        form_layout.setSpacing(18)

        self.input_proj_id = QLineEdit()
        self.input_proj_id.setPlaceholderText("例: sonysonpo_2026")

        self.input_client = QLineEdit()
        self.input_client.setPlaceholderText("例: ソニー損保 様")

        self.input_task = QLineEdit()
        self.input_task.setPlaceholderText("例: GA4リプレイスに伴うパケット検証")

        lbl_p1 = QLabel("フォルダ名 (英数字推奨):")
        lbl_p1.setProperty("class", "bold-label")
        lbl_p2 = QLabel("クライアント名:")
        lbl_p2.setProperty("class", "bold-label")
        lbl_p3 = QLabel("検証タスク名:")
        lbl_p3.setProperty("class", "bold-label")

        form_layout.addRow(lbl_p1, self.input_proj_id)
        form_layout.addRow(lbl_p2, self.input_client)
        form_layout.addRow(lbl_p3, self.input_task)

        layout.addWidget(form_frame)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        self.btn_cancel_proj = QPushButton("キャンセル")
        self.btn_cancel_proj.setObjectName("secondaryBtn")
        self.btn_cancel_proj.setCursor(Qt.PointingHandCursor)
        
        self.btn_confirm_proj = QPushButton("CREATE (作成)")
        self.btn_confirm_proj.setObjectName("primaryBtn")
        self.btn_confirm_proj.setCursor(Qt.PointingHandCursor)

        btn_layout.addWidget(self.btn_cancel_proj)
        btn_layout.addWidget(self.btn_confirm_proj)
        layout.addLayout(btn_layout)

        self.stacked_widget.addWidget(create_widget)