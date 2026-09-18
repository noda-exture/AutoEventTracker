from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QComboBox, QTextEdit, QProgressBar,
                               QTabWidget, QStackedWidget, QFormLayout, QGridLayout,
                               QFrame, QCheckBox, QSizePolicy)
from PySide6.QtCore import Qt

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


# ==========================================
# UIレイアウト構築クラス
# ==========================================

class Ui_MainWindow:
    def setupUi(self, main_window):
        main_window.setWindowTitle("AutoEventTracker")
        main_window.setMinimumSize(920, 760)
        main_window.resize(1040, 880)

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

        self.combo_proj = QComboBox()
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

        # タブエリア
        self.tabs = QTabWidget()
        self.tabs.setObjectName("workspaceTabs")
        self.tabs.setDocumentMode(True)
        self.tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.tabs.addTab(self._create_analysis_tab(), "計測データ比較")
        self.tabs.addTab(self._create_execution_tab(), "シナリオ実行")
        self.tabs.addTab(self._create_scenario_tab(), "シナリオ作成")
        layout.addWidget(self.tabs)

        # 処理ログ
        lbl_log = QLabel("処理ログ")
        lbl_log.setObjectName("logTitle")
        layout.addWidget(lbl_log)

        self.txt_log = QTextEdit()
        self.txt_log.setObjectName("logConsole")
        self.txt_log.setReadOnly(True)
        layout.addWidget(self.txt_log, stretch=1)

        self.stacked_widget.addWidget(main_widget)

    # --- 分析タブ ---
    def _create_analysis_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 24, 20, 20)

        lbl_f1 = QLabel("最新の計測データ")
        lbl_f1.setProperty("class", "bold-label")
        layout.addWidget(lbl_f1)

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        self.txt_f1 = DragDropLineEdit()
        self.txt_f1.setPlaceholderText("ファイルをドラッグ＆ドロップ...")
        self.btn_f1 = QPushButton("選択")
        self.btn_f1.setObjectName("secondaryBtn")
        row1.addWidget(self.txt_f1)
        row1.addWidget(self.btn_f1)
        layout.addLayout(row1)

        lbl_f2 = QLabel("比較元の計測データ")
        lbl_f2.setProperty("class", "bold-label")
        layout.addWidget(lbl_f2)

        row2 = QHBoxLayout()
        row2.setSpacing(10)
        self.txt_f2 = DragDropLineEdit()
        self.txt_f2.setPlaceholderText("ファイルをドラッグ＆ドロップ...")
        self.btn_f2 = QPushButton("選択")
        self.btn_f2.setObjectName("secondaryBtn")
        row2.addWidget(self.txt_f2)
        row2.addWidget(self.btn_f2)
        layout.addLayout(row2)

        lbl_out = QLabel("出力するExcelファイル名:")
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
        self.btn_run_analysis = QPushButton("比較レポートを生成")
        self.btn_run_analysis.setObjectName("primaryBtn")
        self.btn_run_analysis.setCursor(Qt.PointingHandCursor)
        
        self.btn_open = QPushButton("出力フォルダを開く")
        self.btn_open.setObjectName("secondaryBtn")
        self.btn_open.setCursor(Qt.PointingHandCursor)

        btn_row.addWidget(self.btn_run_analysis, stretch=3)
        btn_row.addWidget(self.btn_open, stretch=1)
        layout.addLayout(btn_row)
        layout.addStretch()

        return tab

    # --- シナリオ実行タブ ---
    def _create_execution_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setAlignment(Qt.AlignTop)
        layout.setContentsMargins(20, 24, 20, 20)
        layout.setSpacing(16)

        lbl_exec = QLabel("実行するシナリオ:")
        lbl_exec.setProperty("class", "bold-label")
        layout.addWidget(lbl_exec)

        exec_header = QHBoxLayout()
        exec_header.setSpacing(16)
        self.combo_scenario = QComboBox()
        exec_header.addWidget(self.combo_scenario, stretch=2)

        self.chk_headless = QCheckBox("ブラウザを表示せずに実行")
        exec_header.addWidget(self.chk_headless, stretch=1)
        layout.addLayout(exec_header)

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

        # 値ラベル：セル幅いっぱいに引き伸ばす（alignment 引数を外す）
        self.lbl_info_name = QLabel("-")
        self.lbl_info_name.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        
        self.lbl_info_url = QLabel("-")
        self.lbl_info_url.setObjectName("infoUrlLabel")
        self.lbl_info_url.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_info_url.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        
        self.lbl_info_memo = QLabel("-")
        self.lbl_info_memo.setObjectName("infoMemoLabel")
        self.lbl_info_memo.setWordWrap(True)
        self.lbl_info_memo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # グリッドへ配置（右側ラベルは横幅いっぱいに拡張）
        info_layout.addWidget(lbl_i1, 0, 0, Qt.AlignTop)
        info_layout.addWidget(self.lbl_info_name, 0, 1)

        info_layout.addWidget(lbl_i2, 1, 0, Qt.AlignTop)
        info_layout.addWidget(self.lbl_info_url, 1, 1)

        info_layout.addWidget(lbl_i3, 2, 0, Qt.AlignTop)
        info_layout.addWidget(self.lbl_info_memo, 2, 1)

        layout.addWidget(self.info_frame)

        self.btn_exec_scenario = QPushButton("シナリオを実行")
        self.btn_exec_scenario.setObjectName("actionBtn")
        self.btn_exec_scenario.setCursor(Qt.PointingHandCursor)
        layout.addWidget(self.btn_exec_scenario)

        return tab

    # --- シナリオ作成タブ ---
    def _create_scenario_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setAlignment(Qt.AlignTop)
        layout.setContentsMargins(20, 24, 20, 20)
        layout.setSpacing(14)

        lbl_s1 = QLabel("① シナリオファイル名:")
        lbl_s1.setProperty("class", "bold-label")
        layout.addWidget(lbl_s1)

        self.txt_scenario_file_auto = QLineEdit()
        self.txt_scenario_file_auto.setPlaceholderText("例: my_scenario.json")
        layout.addWidget(self.txt_scenario_file_auto)

        lbl_s2 = QLabel("② 記録を開始するURL:")
        lbl_s2.setProperty("class", "bold-label")
        layout.addWidget(lbl_s2)

        self.txt_url_auto = QLineEdit()
        self.txt_url_auto.setPlaceholderText("例: https://shop.example.com/")
        layout.addWidget(self.txt_url_auto)

        lbl_s3 = QLabel("③ シナリオの概要（任意）:")
        lbl_s3.setProperty("class", "bold-label")
        layout.addWidget(lbl_s3)

        self.txt_memo_auto = QLineEdit()
        self.txt_memo_auto.setPlaceholderText("例: 新規会員登録から購入完了までの正常系フロー")
        layout.addWidget(self.txt_memo_auto)

        layout.addSpacing(6)
        self.btn_record_auto = QPushButton("ブラウザ操作の記録を開始")
        self.btn_record_auto.setObjectName("dangerBtn")
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

        lbl_p1 = QLabel("プロジェクトID（半角英数字推奨）:")
        lbl_p1.setProperty("class", "bold-label")
        lbl_p2 = QLabel("クライアント名:")
        lbl_p2.setProperty("class", "bold-label")
        lbl_p3 = QLabel("検証タスク名:")
        lbl_p3.setProperty("class", "bold-label")

        form_layout.addRow(lbl_p1, self.input_proj_id)
        form_layout.addRow(lbl_p2, self.input_client)
        form_layout.addRow(lbl_p3, self.input_task)

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
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        
        self.btn_cancel_proj = QPushButton("キャンセル")
        self.btn_cancel_proj.setObjectName("secondaryBtn")
        self.btn_cancel_proj.setCursor(Qt.PointingHandCursor)
        
        self.btn_confirm_proj = QPushButton("プロジェクトを作成")
        self.btn_confirm_proj.setObjectName("primaryBtn")
        self.btn_confirm_proj.setCursor(Qt.PointingHandCursor)

        btn_layout.addWidget(self.btn_cancel_proj)
        btn_layout.addWidget(self.btn_confirm_proj)
        layout.addLayout(btn_layout)

        self.stacked_widget.addWidget(create_widget)
