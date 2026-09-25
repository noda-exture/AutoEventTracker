import os
import sys
import json
import time
import re
from urllib.parse import parse_qs, parse_qsl, urlencode, urlparse, urlsplit, urlunsplit
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


def wait_for_dom_stable(page, quiet_ms=600, max_wait_ms=5000):
    """Wait until document and open Shadow DOM mutations have stopped briefly."""
    try:
        page.evaluate(
            """
            ({ quietMs, maxWaitMs }) => new Promise((resolve) => {
                let quietTimer;
                let finished = false;
                const finish = () => {
                    if (finished) return;
                    finished = true;
                    observer.disconnect();
                    clearTimeout(quietTimer);
                    clearTimeout(maxTimer);
                    resolve();
                };
                const armQuietTimer = () => {
                    clearTimeout(quietTimer);
                    quietTimer = setTimeout(finish, quietMs);
                };
                const observer = new MutationObserver((mutations) => {
                    armQuietTimer();
                    for (const mutation of mutations) {
                        for (const node of mutation.addedNodes) observeOpenShadowRoots(node);
                    }
                });
                const options = { childList: true, subtree: true, attributes: true };
                const observedRoots = new WeakSet();
                const observeRoot = (root) => {
                    if (!root || observedRoots.has(root)) return;
                    observer.observe(root, options);
                    observedRoots.add(root);
                };
                const observeOpenShadowRoots = (node) => {
                    if (!(node instanceof Element) && !(node instanceof Document)) return;
                    if (node.shadowRoot) observeRoot(node.shadowRoot);
                    for (const element of node.querySelectorAll?.('*') || []) {
                        if (element.shadowRoot) observeRoot(element.shadowRoot);
                    }
                };
                observeRoot(document.documentElement);
                observeOpenShadowRoots(document);
                const maxTimer = setTimeout(finish, maxWaitMs);
                armQuietTimer();
            })
            """,
            {"quietMs": quiet_ms, "maxWaitMs": max_wait_ms},
        )
    except Exception:
        # Navigation or page closure may destroy the execution context.
        return


def scroll_page(page, value, target_locator=None):
    """Scroll the window or a recorded scroll container."""
    if target_locator is not None:
        if isinstance(value, dict):
            x = int(value.get("x", 0) or 0)
            y = int(value.get("y", 0) or 0)
            target_locator.evaluate("(el, position) => el.scrollTo(position.x, position.y)", {"x": x, "y": y})
        else:
            target_locator.evaluate("(el, amount) => el.scrollBy(0, amount)", int(value or 0))
        return

    if isinstance(value, dict):
        x = int(value.get("x", 0) or 0)
        y = int(value.get("y", 0) or 0)
        page.evaluate("([x, y]) => window.scrollTo(x, y)", [x, y])
        return

    amount = int(value or 0)
    page.evaluate("amount => window.scrollBy(0, amount)", amount)


def select_value(locator, value, timeout_ms=15000):
    """Select and verify an option value."""
    expected = str(value)
    locator.select_option(value=expected, timeout=timeout_ms)
    actual = locator.input_value(timeout=timeout_ms)
    if actual != expected:
        raise RuntimeError(f"プルダウンの値を設定できませんでした（期待値: {expected}、実際: {actual}）")


def fill_value(locator, value, timeout_ms=15000):
    """Fill and verify a text field before moving focus away."""
    expected = "" if value is None else str(value)
    locator.click(timeout=timeout_ms)
    locator.fill(expected, timeout=timeout_ms)
    actual = locator.input_value(timeout=timeout_ms)
    if actual != expected:
        locator.press("ControlOrMeta+A", timeout=timeout_ms)
        locator.type(expected, delay=30, timeout=timeout_ms)
        actual = locator.input_value(timeout=timeout_ms)
    if actual != expected:
        raise RuntimeError(f"テキスト欄の値を設定できませんでした（期待値: {expected}、実際: {actual}）")
    locator.press("Tab", timeout=timeout_ms)
    actual_after_blur = locator.input_value(timeout=timeout_ms)
    if actual_after_blur != expected:
        raise RuntimeError(
            f"テキスト欄の値がフォーカス移動後に変化しました（期待値: {expected}、実際: {actual_after_blur}）"
        )


def _locator_scopes(page):
    """Return the page and its child frames, tolerating simple test doubles."""
    scopes = [page]
    try:
        for frame in page.frames:
            if frame not in scopes:
                scopes.append(frame)
    except (AttributeError, TypeError):
        pass
    return scopes


def _advance_scroll_surfaces(page, amount, direction):
    """Advance the window and visible scroll containers; return whether one moved."""
    return bool(page.evaluate(
        """
        ({ amount, direction }) => {
            const delta = Math.abs(amount) * direction;
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                const style = getComputedStyle(el);
                return rect.width > 0 && rect.height > 0
                    && style.visibility !== 'hidden' && style.display !== 'none';
            };
            const containers = Array.from(document.querySelectorAll('*')).filter((el) => {
                const style = getComputedStyle(el);
                return visible(el)
                    && /(auto|scroll|overlay)/.test(style.overflowY)
                    && el.scrollHeight > el.clientHeight + 2;
            }).sort((a, b) => (b.clientWidth * b.clientHeight) - (a.clientWidth * a.clientHeight));
            const surfaces = [document.scrollingElement, ...containers.slice(0, 8)].filter(Boolean);
            let moved = false;
            for (const surface of surfaces) {
                const before = surface.scrollTop;
                surface.scrollTop += delta;
                if (surface.scrollTop !== before) moved = true;
            }
            return moved;
        }
        """,
        {"amount": amount, "direction": direction},
    ))


def _whitespace_tolerant_text_candidate(scope, selector, max_candidates=200):
    """Resolve :has-text selectors even when rendered line breaks omit DOM whitespace."""
    match = re.fullmatch(r'(?P<tag>[a-zA-Z][\w-]*):has-text\("(?P<text>.*)"\)', selector)
    if not match:
        return None

    expected = match.group("text").replace('\\"', '"').replace("\\\\", "\\")
    expected_without_space = re.sub(r"\s+", "", expected)
    if not expected_without_space:
        return None

    candidates = scope.locator(match.group("tag"))
    for index in range(min(candidates.count(), max_candidates)):
        candidate = candidates.nth(index)
        try:
            text_matches = candidate.evaluate(
                """
                (el, expected) => {
                    const actual = (el.innerText || el.textContent || '').replace(/\s+/g, '');
                    return actual.includes(expected);
                }
                """,
                expected_without_space,
            )
            if text_matches and candidate.is_visible() and candidate.is_enabled():
                scroll_into_view = getattr(candidate, "scroll_into_view_if_needed", None)
                if callable(scroll_into_view):
                    scroll_into_view(timeout=2000)
                return candidate
        except Exception:
            continue
    return None


def _is_tracking_query_key(key):
    lowered = key.lower()
    return (
        lowered in {"_gl", "_ga", "_gcl_au", "_fplc", "gclid", "fbclid", "msclkid"}
        or lowered.startswith("_ga_")
        or lowered.startswith("utm_")
    )


def _canonical_url_without_tracking(url):
    parsed = urlsplit(url)
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    stable_pairs = [(key, value) for key, value in query_pairs if not _is_tracking_query_key(key)]
    removed_tracking = len(stable_pairs) != len(query_pairs)
    canonical = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(stable_pairs), parsed.fragment))
    return canonical, removed_tracking


def _tracking_tolerant_href_candidate(scope, selector, max_candidates=500):
    """Resolve recorded links after analytics query parameters have changed."""
    match = re.fullmatch(r'a\[href="(?P<href>.*)"\]', selector)
    if not match:
        return None

    expected_href = match.group("href").replace('\\"', '"').replace("\\\\", "\\")
    expected_canonical, had_tracking = _canonical_url_without_tracking(expected_href)
    if not had_tracking:
        return None

    candidates = scope.locator("a[href]")
    for index in range(min(candidates.count(), max_candidates)):
        candidate = candidates.nth(index)
        try:
            actual_href = candidate.evaluate("el => el.href")
            actual_canonical, _ = _canonical_url_without_tracking(actual_href)
            if (
                actual_canonical == expected_canonical
                and candidate.is_visible()
                and candidate.is_enabled()
            ):
                scroll_into_view = getattr(candidate, "scroll_into_view_if_needed", None)
                if callable(scroll_into_view):
                    scroll_into_view(timeout=2000)
                return candidate
        except Exception:
            continue
    return None


def wait_for_actionable_locator(page, selector, timeout_ms=30000, scroll_step_px=600, max_candidates=20):
    """Find an actionable target across frames and scroll surfaces in both directions."""
    deadline = time.monotonic() + timeout_ms / 1000
    scroll_started = False
    direction = 1
    last_direction_change = time.monotonic()

    while time.monotonic() < deadline:
        for scope in _locator_scopes(page):
            try:
                locator = scope.locator(selector)
                candidate_count = locator.count()
            except Exception:
                continue
            for index in range(min(candidate_count, max_candidates)):
                candidate = locator.nth(index)
                try:
                    if candidate.is_visible() and candidate.is_enabled():
                        scroll_into_view = getattr(candidate, "scroll_into_view_if_needed", None)
                        if callable(scroll_into_view):
                            scroll_into_view(timeout=2000)
                        return candidate

                    details = candidate.evaluate(
                        "el => ({ tag: el.tagName.toLowerCase(), type: el.type || '', id: el.id || '' })"
                    )
                    if details["tag"] == "input" and details["type"] in ("radio", "checkbox") and details["id"]:
                        escaped_id = details["id"].replace("\\", "\\\\").replace('"', '\\"')
                        labels = scope.locator(f'label[for="{escaped_id}"]')
                        for label_index in range(min(labels.count(), max_candidates)):
                            label = labels.nth(label_index)
                            if label.is_visible() and label.is_enabled():
                                scroll_into_view = getattr(label, "scroll_into_view_if_needed", None)
                                if callable(scroll_into_view):
                                    scroll_into_view(timeout=2000)
                                return label
                except Exception:
                    continue

            tolerant_candidate = _whitespace_tolerant_text_candidate(scope, selector)
            if tolerant_candidate is not None:
                print(f"      [Wait] 改行・空白の差を吸収して要素を特定しました: {selector}")
                return tolerant_candidate

            tolerant_candidate = _tracking_tolerant_href_candidate(scope, selector)
            if tolerant_candidate is not None:
                print(f"      [Wait] 変動する計測用URLパラメータを除外して要素を特定しました: {selector}")
                return tolerant_candidate

        if not scroll_started:
            print(f"      [Wait] 要素の描画を待ちながら自動スクロールします: {selector}")
            scroll_started = True

        moved = False
        for scope in _locator_scopes(page):
            try:
                moved = _advance_scroll_surfaces(scope, scroll_step_px, direction) or moved
            except Exception:
                continue

        now = time.monotonic()
        if not moved or now - last_direction_change >= max(1.0, timeout_ms / 2000):
            direction *= -1
            last_direction_change = now
        page.wait_for_timeout(250)

    raise RuntimeError(f"操作可能な要素が時間内に表示されませんでした: {selector}")


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
    deadline = time.monotonic() + timeout_ms / 1000
    last_error = None
    while time.monotonic() < deadline:
        candidate_count = locator.count()
        for index in range(min(candidate_count, max_candidates)):
            remaining_ms = int((deadline - time.monotonic()) * 1000)
            if remaining_ms <= 0:
                break

            candidate = locator.nth(index)
            is_visible = getattr(candidate, "is_visible", None)
            if callable(is_visible) and not is_visible():
                continue

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
        time.sleep(0.1)

    if last_error is not None:
        raise last_error
    raise RuntimeError("クリック可能な表示要素が見つかりませんでした。")


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
        return False

    with open(config_path, "r", encoding="utf-8") as f:
        master_config = json.load(f)
    
    combined_steps = prepare_steps(master_config, project_dir)

    if not combined_steps:
        print("エラー: 実行すべきステップが空です。")
        return False

    execution_settings = master_config.get("execution_settings", {})
    element_timeout_ms = int(execution_settings.get("element_timeout_ms", 30000))
    action_timeout_ms = int(execution_settings.get("action_timeout_ms", 15000))
    navigation_timeout_ms = int(execution_settings.get("navigation_timeout_ms", 30000))
    tab_timeout_ms = int(execution_settings.get("tab_timeout_ms", 15000))
    dom_quiet_ms = int(execution_settings.get("dom_quiet_ms", 600))
    dom_stable_timeout_ms = int(execution_settings.get("dom_stable_timeout_ms", 5000))
    scroll_step_px = int(execution_settings.get("scroll_step_px", 600))
    between_steps_ms = int(execution_settings.get("between_steps_ms", 500))

    max_retries = int(execution_settings.get("max_retries", 3))
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

            def wait_for_page_id(page_id, timeout_ms=tab_timeout_ms):
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
                page.goto(master_config.get('start_url', ''), timeout=navigation_timeout_ms)
                page.wait_for_load_state("domcontentloaded")
                wait_for_dom_stable(page, dom_quiet_ms, dom_stable_timeout_ms)
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
                        settle_page.wait_for_timeout(between_steps_ms)

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
                            page.wait_for_load_state("load", timeout=navigation_timeout_ms)
                            print("         -> ページのロード完了を確認しました。")
                        except Exception:
                            print("         -> ロード待ちがタイムアウトしました。処理を続行します。")
                        wait_for_dom_stable(page, dom_quiet_ms, dom_stable_timeout_ms)
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
                        try:
                            if action == "wait_for" and step.get("state", "visible") != "visible":
                                target_loc = page.locator(selector).first
                                target_loc.wait_for(
                                    state=step.get("state", "attached"),
                                    timeout=int(step.get("timeout_ms", element_timeout_ms)),
                                )
                            else:
                                target_loc = wait_for_actionable_locator(
                                    page,
                                    selector,
                                    timeout_ms=int(step.get("timeout_ms", element_timeout_ms)),
                                    scroll_step_px=scroll_step_px,
                                )
                        except Exception as e_timeout:
                            match = re.search(r'\[name="(.*?)"\]', selector)
                            if match:
                                fallback_text = match.group(1)
                                print(f"      セレクタが見つかりません。テキスト『{fallback_text}』で曖昧検索に切り替えます...")
                                target_loc = wait_for_actionable_locator(
                                    page,
                                    f'text="{fallback_text}"',
                                    timeout_ms=5000,
                                    scroll_step_px=scroll_step_px,
                                )
                            else:
                                raise e_timeout
                        
                    if action == "click":
                        click_first_actionable(target_loc, timeout_ms=action_timeout_ms)

                    elif action == "change" or action == "select":
                        element_tag = target_loc.evaluate("el => el.tagName.toLowerCase()")
                        if element_tag == "select":
                            select_value(target_loc, value, timeout_ms=action_timeout_ms)
                            print(f"      選択肢 [{value}] をセレクトボックスから選択しました。")
                        else:
                            fill_value(target_loc, value, timeout_ms=action_timeout_ms)
                            
                    elif action == "fill":
                        fill_value(target_loc, value, timeout_ms=action_timeout_ms)
                        print(f"      テキスト欄に [{value}] を入力しました。")

                    elif action == "scroll":
                        scroll_page(page, value, target_loc)

                    elif action == "wait":
                        page.wait_for_timeout(int(value or step.get("timeout_ms", 1000)))

                    elif action == "wait_for":
                        pass

                    wait_for_dom_stable(page, dom_quiet_ms, dom_stable_timeout_ms)
                    
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

    return success

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
        
    sys.exit(0 if run_tracker(p_name, t_file, headless=is_headless) else 1)
