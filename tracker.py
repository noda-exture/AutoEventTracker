import os
import sys
import json
import time
import re
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright

def run_tracker(project_name, config_filename, headless=False):
    """
    Args:
        project_name (str): 案件名（例: 'sonysonpo', 'ex-ture'）
        config_filename (str): 中間JSONのファイル名（例: 'master_A.json'）
        headless (bool): 画面を表示せずに実行するかどうか
    """
    # 📁 新しい案件別ディレクトリ構造のパスを構築
    project_dir = os.path.join("project", project_name)
    config_path = os.path.join(project_dir, "scenario", config_filename)
    
    if not os.path.exists(config_path):
        print(f"❌ エラー: 設定ファイル '{config_path}' が見つかりません。")
        return

    with open(config_path, "r", encoding="utf-8") as f:
        master_config = json.load(f)
    
    combined_steps = []
    
    # パターンA: 中間JSONに "include_parts" がある場合、パーツを順に読み込んで結合
    if "include_parts" in master_config:
        print(f"📦 パーツJSONの結合を開始します...")
        for part_rel_path in master_config["include_parts"]:
            # 各パーツファイルの絶対パスを構築
            part_path = os.path.join(project_dir, "parts", part_rel_path)
            
            if os.path.exists(part_path):
                with open(part_path, "r", encoding="utf-8") as f:
                    part_data = json.load(f)
                    if "steps" in part_data:
                        combined_steps.extend(part_data["steps"])
                        print(f"   🔗 結合成功: {part_rel_path} ({len(part_data['steps'])} steps)")
            else:
                print(f"   ❌ エラー: パーツファイル '{part_path}' が見つかりません。処理を中断します。")
                return
    else:
        # パターンB: 中間JSON自体に直接 "steps" が書かれている従来型への互換性ケア
        combined_steps = master_config.get("steps", [])

    if not combined_steps:
        print("❌ エラー: 実行すべきステップが空です。")
        return

    # 🚀 最大3回のリトライループを設定
    max_retries = 3
    success = False

    for attempt in range(max_retries):
        print(f"\n🔄 シナリオ実行試行 [{attempt + 1} / {max_retries}] ───")
        
        analytics_logs = []
        # 💡 現在実行中のステップインデックス（Phase2用マトリクス突合のキー）
        current_step_index = 0

        # 📥 ネットワークリクエストを監視するコールバック関数
        def handle_request(request):
            url = request.url
            method = request.method
            
            # ① GA4の通信を検知
            if "google-analytics.com/g/collect" in url or "google-analytics.com/collect" in url:
                parsed_url = urlparse(url)
                params = parse_qs(parsed_url.query)
                post_data = request.post_data if method == "POST" else None
                
                log_entry = {
                    "type": "GA4",
                    "step_index": current_step_index, # 💡 現在のステップ番号を刻印
                    "method": method,
                    "url": url,
                    "params": {k: v[0] for k, v in params.items()},
                    "post_data": post_data,
                    "timestamp": time.time()
                }
                analytics_logs.append(log_entry)
                print("   📊 [GA4 検知] イベントが送信されました")

            # ② 従来型 Adobe Analytics の通信を検知
            elif "/b/ss/" in url or ".2o7.net" in url or ".sc.omtrdc.net" in url:
                parsed_url = urlparse(url)
                params = parse_qs(parsed_url.query)
                
                log_entry = {
                    "type": "Adobe Analytics (Legacy)",
                    "step_index": current_step_index, # 💡 現在のステップ番号を刻印
                    "method": method,
                    "url": url,
                    "params": {k: v[0] for k, v in params.items()},
                    "timestamp": time.time()
                }
                analytics_logs.append(log_entry)
                print("   🔺 [Adobe Analytics 検知] ビーコンが送信されました")

            # ③ AEP Web SDK (Adobe Edge Network) の通信を検知
            elif "edge.adobedc.net" in url and "/v1/" in url:
                xdm_payload = None
                if method == "POST" and request.post_data:
                    try:
                        xdm_payload = json.loads(request.post_data)
                    except Exception:
                        xdm_payload = request.post_data

                log_entry = {
                    "type": "AEP Web SDK",
                    "step_index": current_step_index, # 💡 現在のステップ番号を刻印
                    "method": method,
                    "url": url,
                    "xdm_payload": xdm_payload,
                    "timestamp": time.time()
                }
                analytics_logs.append(log_entry)
                print("   🌐 [AEP Web SDK 検知] Edge Networkへの通信をキャッチしました")

        output_dir = os.path.join(project_dir, "outputs")
        os.makedirs(output_dir, exist_ok=True)
        
        from datetime import datetime
        current_time = datetime.now().strftime("%Y%m%d_%H%M")
        
        base_filename = master_config.get("output_file", config_filename.replace(".json", "_result.json"))
        output_filename = f"{current_time}_{base_filename}"
        output_path = os.path.join(output_dir, output_filename)

        step_error_occurred = False 

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--use-fake-ui-for-media-stream"
                ]
            ) 
            
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800}
            )
            
            context.on("request", handle_request)
            page = context.new_page()
            
            windows = {"main": page}
            latest_opened_window = None
            
            print(f"🚀 シナリオ開始: {config_filename} (Project: {project_name})")
            print(f"🔗 開始URL: {master_config.get('start_url', '未設定')}")
            
            try:
                page.goto(master_config.get('start_url', ''))
                page.wait_for_load_state("domcontentloaded")
            except Exception as e:
                print(f"   ❌ 初期ページの読み込みでエラーが発生しました: {e}")
                browser.close()
                continue
            
            for i, step in enumerate(combined_steps):
                current_step_index = i # 💡 グローバル変数に現在のステップ番号をセット
                action = step["action"]
                selector = step.get("selector")
                value = step.get("value")
                memo = step.get("memo", "")
                
                step_log = f" └ [Step {i+1}] {action} -> {selector if selector else ''}"
                if memo:
                    step_log += f" 💬 ({memo})"
                print(step_log)
                
                try:
                    page.wait_for_timeout(1000)

                    if action == "switch_window":
                        target_name = value
                        if target_name in windows and windows[target_name] is not None:
                            page = windows[target_name]
                            page.bring_to_front()
                            print(f"      🔄 操作対象を既存の [{target_name}] ウィンドウに切り替えました。")
                        elif latest_opened_window is not None:
                            windows[target_name] = latest_opened_window
                            page = windows[target_name]
                            page.bring_to_front()
                            latest_opened_window = None
                            print(f"      🏷️ 新しいウィンドウに [{target_name}] と名付けて登録・切り替えました。")
                        else:
                            print(f"      ❌ エラー: 指定されたウィンドウ [{target_name}] が存在しません。")
                            step_error_occurred = True
                            break

                        print("      ⏳ [Wait] 遷移先ページの読み込みを待っています...")
                        try:
                            page.wait_for_load_state("load", timeout=15000)
                            print("         -> 🔗 ページのロード完了を確認しました。")
                        except Exception:
                            print("         -> ⚠️ ロード待ちがタイムアウトしました。処理を続行します。")
                        continue

                    target_loc = None
                    if selector:
                        target_loc = page.locator(selector).first
                        try:
                            target_loc.wait_for(state="attached", timeout=10000)
                        except Exception as e_timeout:
                            match = re.search(r'\[name="(.*?)"\]', selector)
                            if match:
                                fallback_text = match.group(1)
                                print(f"      ⚠️ セレクタが見つかりません。テキスト『{fallback_text}』で曖昧検索に切り替えます...")
                                target_loc = page.locator(f'text="{fallback_text}"').first
                                target_loc.wait_for(state="attached", timeout=5000)
                            else:
                                raise e_timeout
                        
                    before_count = len(analytics_logs)
                    
                    if action == "click":
                        try:
                            with context.expect_page(timeout=2000) as new_page_info:
                                target_loc.click(timeout=15000)
                            if new_page_info.value:
                                print("      🔗 [Window] 新しい別ウィンドウの開きを検知しました。")
                                latest_opened_window = new_page_info.value
                        except Exception:
                            pass
                            
                    elif action == "change" or action == "select":
                        element_tag = target_loc.evaluate("el => el.tagName.toLowerCase()")
                        if element_tag == "select":
                            target_loc.select_option(value=value, timeout=15000)
                            print(f"      選択肢 [{value}] をセレクトボックスから選択しました。")
                        else:
                            target_loc.fill(value, timeout=15000)
                            target_loc.press("Enter")
                            
                    elif action == "fill":
                        target_loc.fill(value, timeout=15000)
                        target_loc.press("Tab")
                    
                    after_count = len(analytics_logs)
                    print(f"      (このステップで検知した計測通信: {after_count - before_count} 件)")
                    
                except Exception as e:
                    print(f"   ❌ エラー発生: {e}")
                    step_error_occurred = True
                    break 

            if not step_error_occurred:
                output_data = {
                    "project": project_name,
                    "scenario": config_filename,
                    "memo": master_config.get("memo", ""),
                    "executed_steps": combined_steps,
                    "total_events_captured": len(analytics_logs),
                    "events": analytics_logs
                }
                
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(output_data, f, ensure_ascii=False, indent=2)
                    
                print(f"\n🎉 すべての工程が成功しました！")
                print(f"📝 計測データを保存しました: {output_path}\n")
                
                success = True
                if not headless:
                    page.pause()
                browser.close()
                break 
            else:
                print("   ⚠️ ステップ実行中にエラーがあったため、このブラウザを閉じてリトライします。")
                browser.close()

        if success:
            break
    else:
        print(f"\n❌ エラー: {max_retries}回リトライしましたが、シナリオを正常に完走できませんでした。")

if __name__ == "__main__":
    p_name = "example_project"
    t_file = "test.json"
    is_headless = False
    
    if len(sys.argv) > 2:
        p_name = sys.argv[1]
        t_file = sys.argv[2]
    
    if len(sys.argv) > 3:
        if sys.argv[3] == "--headless":
            is_headless = True
        
    run_tracker(p_name, t_file, headless=is_headless)