import os
import sys
import json
import time
import re
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright

def _safe_step_token(value):
    token = re.sub(r"[^\w-]+", "_", str(value or ""), flags=re.UNICODE).strip("_")
    return token or "step"


def _normalize_step_id(value, fallback):
    step_id = _safe_step_token(value or fallback)
    if step_id.startswith("step_") and len(step_id) > len("step_"):
        step_id = step_id[len("step_"):]
    return step_id


def prepare_steps(master_config, project_dir):
    """Load scenario steps and ensure every step has a stable, unique ID."""
    loaded_steps = []

    if "include_parts" in master_config:
        print("パーツJSONの結合を開始します...")
        for part_rel_path in master_config["include_parts"]:
            part_path = os.path.join(project_dir, "parts", part_rel_path)
            if not os.path.exists(part_path):
                print(f"   エラー: パーツファイル '{part_path}' が見つかりません。処理を中断します。")
                return []

            with open(part_path, "r", encoding="utf-8") as f:
                part_data = json.load(f)

            part_steps = part_data.get("steps", [])
            part_token = _safe_step_token(os.path.splitext(part_rel_path)[0])
            for local_index, raw_step in enumerate(part_steps):
                step = dict(raw_step)
                local_id = _normalize_step_id(step.get("step_id"), f"{local_index + 1:04d}")
                step["step_id"] = f"{part_token}__{local_id}"
                loaded_steps.append(step)
            print(f"   結合成功: {part_rel_path} ({len(part_steps)} steps)")
    else:
        loaded_steps = [dict(step) for step in master_config.get("steps", [])]

    prepared_steps = []
    used_ids = set()
    for index, step in enumerate(loaded_steps):
        base_id = _normalize_step_id(step.get("step_id"), f"{index + 1:04d}")
        step_id = base_id
        suffix = 2
        while step_id in used_ids:
            step_id = f"{base_id}_{suffix}"
            suffix += 1
        used_ids.add(step_id)

        step["step_id"] = step_id
        step["step_name"] = step.get("step_name") or step.get("memo") or step.get("action", f"Step {index + 1}")
        prepared_steps.append(step)

    return prepared_steps


def wait_for_analytics_quiet(page, capture_state, quiet_ms=800, max_wait_ms=3000):
    """Wait until analytics traffic has been quiet long enough for the active step."""
    started_at = time.monotonic()
    while True:
        now = time.monotonic()
        last_request_at = capture_state.get("last_request_at") or started_at
        if (now - last_request_at) * 1000 >= quiet_ms:
            return
        if (now - started_at) * 1000 >= max_wait_ms:
            return
        page.wait_for_timeout(100)


class PageRegistry:
    """Keep stable page IDs that match the order used by the scenario recorder."""

    def __init__(self, main_page):
        self.pages = {"main": main_page}
        self.page_ids = {main_page: "main"}
        self.next_page_number = 1

    def register(self, page):
        existing = self.page_ids.get(page)
        if existing:
            return existing

        page_id = f"page{self.next_page_number}"
        self.next_page_number += 1
        self.pages[page_id] = page
        self.page_ids[page] = page_id
        return page_id

    def page_id_for(self, page):
        return self.page_ids.get(page)

    def get_live(self, page_id):
        page = self.pages.get(page_id)
        if page is None or page.is_closed():
            return None
        return page

    def live_pages(self):
        return {
            page_id: page
            for page_id, page in self.pages.items()
            if not page.is_closed()
        }


def click_first_actionable(locator, timeout_ms=15000, max_candidates=20):
    """Click the first matching element that can actually receive the click."""
    candidate_count = locator.count()
    if candidate_count == 0:
        locator.first.click(timeout=timeout_ms)
        return

    if candidate_count == 1:
        locator.first.click(timeout=timeout_ms)
        return

    deadline = time.monotonic() + timeout_ms / 1000
    last_error = None
    for index in range(min(candidate_count, max_candidates)):
        remaining_ms = int((deadline - time.monotonic()) * 1000)
        if remaining_ms <= 0:
            break

        candidate = locator.nth(index)
        try:
            candidate.click(timeout=min(3000, remaining_ms))
            return
        except Exception as error:
            last_error = error
            message = str(error).lower()
            retryable_actionability_error = any(fragment in message for fragment in (
                "intercepts pointer events",
                "not visible",
                "not enabled",
                "not stable",
                "outside of the viewport",
                "detached from the dom",
            ))
            if not retryable_actionability_error:
                raise

    if last_error is not None:
        raise last_error
    locator.first.click(timeout=timeout_ms)


def run_tracker(project_name, config_filename, headless=False):
    """
    Args:
        project_name (str): 案件名（例: 'sonysonpo', 'ex-ture'）
        config_filename (str): 中間JSONのファイル名（例: 'master_A.json'）
        headless (bool): 画面を表示せずに実行するかどうか
    """
    # 新しい案件別ディレクトリ構造のパスを構築
    project_dir = os.path.join("project", project_name)
    config_path = os.path.join(project_dir, "scenario", config_filename)
    
    if not os.path.exists(config_path):
        print(f"エラー: 設定ファイル '{config_path}' が見つかりません。")
        return

    with open(config_path, "r", encoding="utf-8") as f:
        master_config = json.load(f)
    
    combined_steps = prepare_steps(master_config, project_dir)

    if not combined_steps:
        print("エラー: 実行すべきステップが空です。")
        return

    # 最大3回のリトライループを設定
    max_retries = 3
    success = False

    for attempt in range(max_retries):
        print(f"\nシナリオ実行（{attempt + 1}/{max_retries}回目） ───")
        
        analytics_logs = []
        initial_capture_state = {
            "step_index": -1,
            "step_id": "initial_load",
            "step_name": "開始ページの読み込み",
            "last_request_at": None,
        }
        page_capture_states = {"main": dict(initial_capture_state)}
        packet_indexes_by_step = {}
        runtime_state = {
            "active_page_id": "main",
            "registry": None,
        }

        def append_analytics_log(log_entry, source_page_id):
            capture_state = page_capture_states.get(source_page_id, initial_capture_state)
            packet_key = capture_state["step_id"]
            packet_index = packet_indexes_by_step.get(packet_key, 0)
            log_entry.update({
                "step_index": capture_state["step_index"],
                "step_id": capture_state["step_id"],
                "step_name": capture_state["step_name"],
                "page_id": source_page_id,
                "packet_index_in_step": packet_index,
            })
            packet_indexes_by_step[packet_key] = packet_index + 1
            capture_state["last_request_at"] = time.monotonic()
            analytics_logs.append(log_entry)

        def request_page_id(request):
            registry = runtime_state["registry"]
            if registry is not None:
                try:
                    source_page = request.frame.page
                    page_id = registry.page_id_for(source_page)
                    if page_id:
                        return page_id
                    page_id = registry.register(source_page)
                    parent_state = page_capture_states.get(
                        runtime_state["active_page_id"],
                        initial_capture_state,
                    )
                    page_capture_states[page_id] = dict(parent_state)
                    return page_id
                except Exception:
                    pass
            return runtime_state["active_page_id"]

        # ネットワークリクエストを監視するコールバック関数
        def handle_request(request):
            url = request.url
            method = request.method
            source_page_id = request_page_id(request)
            
            # ① GA4の通信を検知
            if "google-analytics.com/g/collect" in url or "google-analytics.com/collect" in url:
                parsed_url = urlparse(url)
                params = parse_qs(parsed_url.query)
                post_data = request.post_data if method == "POST" else None
                
                log_entry = {
                    "type": "GA4",
                    "method": method,
                    "url": url,
                    "params": {k: v[0] for k, v in params.items()},
                    "post_data": post_data,
                    "timestamp": time.time()
                }
                append_analytics_log(log_entry, source_page_id)
                print("    [GA4 検知] イベントが送信されました")

            # ② 従来型 Adobe Analytics の通信を検知
            elif "/b/ss/" in url or ".2o7.net" in url or ".sc.omtrdc.net" in url:
                parsed_url = urlparse(url)
                params = parse_qs(parsed_url.query)
                
                log_entry = {
                    "type": "Adobe Analytics (Legacy)",
                    "method": method,
                    "url": url,
                    "params": {k: v[0] for k, v in params.items()},
                    "timestamp": time.time()
                }
                append_analytics_log(log_entry, source_page_id)
                print("    [Adobe Analytics 検知] ビーコンが送信されました")

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
                    "method": method,
                    "url": url,
                    "xdm_payload": xdm_payload,
                    "timestamp": time.time()
                }
                append_analytics_log(log_entry, source_page_id)
                print("    [AEP Web SDK 検知] Edge Networkへの通信を検知しました")

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
            registry = PageRegistry(page)
            runtime_state["registry"] = registry

            def register_new_page(new_page):
                page_id = registry.register(new_page)
                if page_id not in page_capture_states:
                    parent_state = page_capture_states.get(
                        runtime_state["active_page_id"],
                        initial_capture_state,
                    )
                    page_capture_states[page_id] = dict(parent_state)
                print(f"      [Tab] 新しいタブ [{page_id}] を登録しました。")
                return page_id

            def wait_for_page_id(page_id, timeout_ms=10000):
                deadline = time.monotonic() + timeout_ms / 1000
                while time.monotonic() < deadline:
                    target_page = registry.get_live(page_id)
                    if target_page is not None:
                        return target_page

                    for candidate in context.pages:
                        if registry.page_id_for(candidate) is None:
                            register_new_page(candidate)

                    pump_page = registry.get_live(runtime_state["active_page_id"])
                    if pump_page is None:
                        live_pages = list(registry.live_pages().values())
                        pump_page = live_pages[0] if live_pages else None
                    if pump_page is None:
                        break
                    pump_page.wait_for_timeout(100)
                return None

            context.on("page", register_new_page)
            
            print(f"シナリオ開始: {config_filename}（プロジェクト: {project_name}）")
            print(f"開始URL: {master_config.get('start_url', '未設定')}")
            
            try:
                page.goto(master_config.get('start_url', ''))
                page.wait_for_load_state("domcontentloaded")
                wait_for_analytics_quiet(page, page_capture_states["main"])
            except Exception as e:
                print(f"   初期ページを読み込めませんでした: {e}")
                browser.close()
                continue
            
            for i, step in enumerate(combined_steps):
                action = step["action"]
                selector = step.get("selector")
                value = step.get("value")
                memo = step.get("memo", "")
                
                step_log = f" └ [Step {i+1}] {action} -> {selector if selector else ''}"
                if memo:
                    step_log += f" | {memo}"
                print(step_log)
                
                try:
                    # 前ステップの遅延通信を前ステップ側で収束させる
                    settle_page = registry.get_live(runtime_state["active_page_id"])
                    if settle_page is not None:
                        settle_page.wait_for_timeout(1000)

                    requested_page_id = step.get("page_id")
                    if action in ("switch_window", "close_window"):
                        requested_page_id = value or requested_page_id
                    target_page_id = requested_page_id or runtime_state["active_page_id"]
                    target_page = wait_for_page_id(target_page_id)
                    if target_page is None:
                        raise RuntimeError(f"指定されたタブ [{target_page_id}] が存在しません。")

                    step_capture_state = {
                        "step_index": i,
                        "step_id": step["step_id"],
                        "step_name": step["step_name"],
                        "last_request_at": None,
                    }
                    page_capture_states[target_page_id] = step_capture_state
                    packet_indexes_by_step[step["step_id"]] = 0
                    before_count = sum(
                        1 for event in analytics_logs
                        if event.get("step_id") == step["step_id"]
                    )

                    if action == "switch_window":
                        page = target_page
                        runtime_state["active_page_id"] = target_page_id
                        page.bring_to_front()
                        print(f"      操作対象を [{target_page_id}] タブに切り替えました。")

                        print("      [Wait] 遷移先ページの読み込みを待っています...")
                        try:
                            page.wait_for_load_state("load", timeout=15000)
                            print("         -> ページのロード完了を確認しました。")
                        except Exception:
                            print("         -> ロード待ちがタイムアウトしました。処理を続行します。")
                        wait_for_analytics_quiet(page, step_capture_state)
                        after_count = sum(
                            1 for event in analytics_logs
                            if event.get("step_id") == step["step_id"]
                        )
                        print(f"      (このステップで検知した計測通信: {after_count - before_count} 件)")
                        continue

                    if action == "close_window":
                        print(f"      [{target_page_id}] タブを閉じます。")
                        target_page.close()
                        remaining_pages = registry.live_pages()
                        next_page_id = "main" if "main" in remaining_pages else next(iter(remaining_pages), None)
                        if next_page_id is not None:
                            page = remaining_pages[next_page_id]
                            runtime_state["active_page_id"] = next_page_id
                            page.bring_to_front()
                        continue

                    page = target_page
                    if runtime_state["active_page_id"] != target_page_id:
                        page.bring_to_front()
                        print(f"      操作対象を [{target_page_id}] タブに自動切り替えしました。")
                    runtime_state["active_page_id"] = target_page_id

                    target_loc = None
                    if selector:
                        target_loc = page.locator(selector)
                        try:
                            target_loc.first.wait_for(state="attached", timeout=10000)
                        except Exception as e_timeout:
                            match = re.search(r'\[name="(.*?)"\]', selector)
                            if match:
                                fallback_text = match.group(1)
                                print(f"      セレクタが見つかりません。テキスト『{fallback_text}』で曖昧検索に切り替えます...")
                                target_loc = page.locator(f'text="{fallback_text}"')
                                target_loc.first.wait_for(state="attached", timeout=5000)
                            else:
                                raise e_timeout
                        
                    if action == "click":
                        click_first_actionable(target_loc, timeout_ms=15000)

                    elif action == "change" or action == "select":
                        target_loc = target_loc.first
                        element_tag = target_loc.evaluate("el => el.tagName.toLowerCase()")
                        if element_tag == "select":
                            target_loc.select_option(value=value, timeout=15000)
                            print(f"      選択肢 [{value}] をセレクトボックスから選択しました。")
                        else:
                            target_loc.fill(value, timeout=15000)
                            target_loc.press("Enter")
                            
                    elif action == "fill":
                        target_loc = target_loc.first
                        target_loc.fill(value, timeout=15000)
                        target_loc.press("Tab")
                    
                    wait_for_analytics_quiet(page, step_capture_state)
                    after_count = sum(
                        1 for event in analytics_logs
                        if event.get("step_id") == step["step_id"]
                    )
                    print(f"      (このステップで検知した計測通信: {after_count - before_count} 件)")
                    
                except Exception as e:
                    print(f"   エラー発生: {e}")
                    step_error_occurred = True
                    break 

            if not step_error_occurred:
                output_data = {
                    "schema_version": 2,
                    "project": project_name,
                    "scenario": config_filename,
                    "memo": master_config.get("memo", ""),
                    "step_capture_mode": "stable_step_id",
                    "tab_capture_mode": "stable_page_id",
                    "scenario_step_ids": [step["step_id"] for step in combined_steps],
                    "executed_steps": combined_steps,
                    "total_events_captured": len(analytics_logs),
                    "events": analytics_logs
                }
                
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(output_data, f, ensure_ascii=False, indent=2)
                    
                print("\nすべての工程が成功しました。")
                print(f"計測データを保存しました: {output_path}\n")
                
                success = True
                if not headless:
                    pause_page = registry.get_live(runtime_state["active_page_id"])
                    if pause_page is not None:
                        pause_page.pause()
                browser.close()
                break 
            else:
                print("   ステップ実行中にエラーがあったため、このブラウザを閉じてリトライします。")
                browser.close()

        if success:
            break
    else:
        print(f"\nエラー: {max_retries}回試行しましたが、シナリオを最後まで実行できませんでした。")

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
