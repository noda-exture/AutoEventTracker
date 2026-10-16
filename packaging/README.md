# インストーラーの作成

対象は macOS Apple Silicon / macOS Intel / Windows x64。Python、Node.js、Chromium、Qt、Excel出力ライブラリを同梱し、利用者による追加インストールは不要です。

- macOS: `.pkg` を開いてインストール後、アプリケーションフォルダの AutoEventTracker を起動。
- Windows: `-setup.exe` を開いてインストール後、スタートメニューから起動。
- macOSは13以降（実際の検証OSはCIログ参照）、Windowsは10/11の64bit版を対象とします。
- 開発者証明書による署名・Apple公証は未設定です。macOSはローカルのアドホック署名のみです。配布先のOSや組織のセキュリティ設定によって起動の確認または制限が発生します。正式配布には署名・公証の追加が必要です。

## 保存先

配布物に既存の `project` フォルダは含めません。共通テンプレートは `create_template.py` から新規生成します。

初回起動時に以下へ空の案件保存領域と共通設定を作成します。更新時に既存データを上書きしません。

- macOS: `~/Library/Application Support/AutoEventTracker/`
- Windows: `%LOCALAPPDATA%\AutoEventTracker\`

その配下の `project` に、新しく作った案件・シナリオ・計測結果・ログを保存します。アンインストール時も利用者のデータは保持します。

## GitHub Actions

`Build installers` ワークフローを使用します。`codex/installers` へのpush、または手動実行で3種類を各OS上でビルドします。成果物はActionsのArtifactsに3日間保存します。公開Releaseの自動作成は行いません。

各OSで依存ライブラリをインストールし、Pythonテスト、実行ファイル作成、同梱ランタイムだけでの動作確認、インストーラー作成を順に行います。`project` が入っていないことも検査します。

## ローカルビルド

Python 3.11とNode.js、およびmacOSのCommand Line ToolsまたはWindowsのInno Setup 6が開発端末に必要です。配布先端末には不要です。

```sh
python -m venv .venv-build
# macOS: source .venv-build/bin/activate
# Windows: .venv-build\Scripts\activate
python -m pip install -r requirements-build.txt
npm ci
python packaging/build_installers.py
```

成果物は `installers/`。SHA-256ファイルと実行ファイルの検証結果JSONも出力します。

検証は一時フォルダを保存先にして、GUI・新規案件テンプレート・同梱Nodeによるブラウザ表示あり/なしの記録・同梱Pythonワーカーによるシナリオ再生と通信取得・Excel生成を行います。外部サイトへの計測通信は送らず、ローカルHTTPサーバーだけを使います。
