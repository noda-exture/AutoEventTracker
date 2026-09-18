import sys
import os
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_page

def main():
    # 💡 GUI(main.py)から渡されたURLを受け取る (引数がなければ空文字)
    start_url = sys.argv[1] if len(sys.argv) > 1 else ""

    # 💡 空で実行した場合、処理終了
    if not start_url:
        print("❌ エラー: 開始URLが指定されていません。処理を終了します。")
        sys.exit(1)

    print(f"🚀 Pythonレコーダー(Codegen)を起動します...")
    print(f"🔗 対象URL: {start_url}")

    try:
        # with構文を使うことで、プログラムが終了またはクラッシュした際に
        # Playwrightが裏側のChromiumプロセスをOSレベルで確実に自動キルしてくれます
        with sync_playwright() as p:
            # ⭕ 有頭（画面あり）でブラウザを起動
            browser = p.chromium.launch(
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled", # 自動操縦フラグを隠す
                    "--use-fake-ui-for-media-stream"
                ]
            )
            
            # ⭕ コンテキスト作成時に人間の環境（Mac Chromeなど）を偽装
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
                locale="ja-JP",
                timezone_id="Asia/Tokyo"
            )
            
            page = context.new_page()

            # ステルスプラグインを適用（Bot検知を回避）
            stealth_page(page)

            # 対象サイトへ移動
            page.goto(start_url)
            
            # 💡 Playwright標準のInspector（Codegenツール）を強制的に起動させる
            print("💡 Playwright インスペクターが起動しました。操作を終了する場合はブラウザを閉じてください。")
            page.pause()
            
            # 💡 ユーザーがブラウザを閉じたら、with構文を抜けて安全に終了します
            print("🛑 ブラウザが閉じられました。プロセスを安全に終了します。")
            
    except Exception as e:
        print(f"❌ 実行エラー: {str(e)}")

if __name__ == "__main__":
    main()
