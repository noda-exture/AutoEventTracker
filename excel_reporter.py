import os
import sys
import json
import urllib.parse
from datetime import datetime
from itertools import zip_longest
from openpyxl import load_workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

def load_project_config(project_dir):
    config_path = os.path.join(project_dir, "config.json")
    default_config = {
        "client_name": "クライアント名未設定",
        "task_name": "課題名未設定",
        "excel_setting": {
            "font_name": "游ゴシック",
            "theme_color_new": "E2EFDA",
            "theme_color_old": "FFF2CC",
            "diff_color": "FFC7CE",
            "diff_font_color": "9C0006"
        },
        "extraction_rules": {
            "ignore_params": ["_ts", "gtm_auth", "gjid", "gtm", "requestId", "configId"],
            "nested_separator": "."
        }
    }
    
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            user_config = json.load(f)
            if "excel_setting" in user_config:
                default_config["excel_setting"].update(user_config["excel_setting"])
            if "extraction_rules" in user_config:
                default_config["extraction_rules"].update(user_config["extraction_rules"])
            default_config.update({k: v for k, v in user_config.items() if k not in ["excel_setting", "extraction_rules"]})
            
    return default_config

def replace_placeholders_in_sheet(ws, config):
    today_str = datetime.now().strftime("%Y年%m月%d日")
    placeholders = {
        "{client_name}": config.get("client_name", ""),
        "{task_name}": config.get("task_name", ""),
        "{date}": today_str
    }
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, min_col=1, max_col=ws.max_column):
        for cell in row:
            if cell.value and isinstance(cell.value, str):
                val_str = cell.value
                for placeholder, actual_value in placeholders.items():
                    if placeholder in val_str:
                        val_str = val_str.replace(placeholder, actual_value)
                cell.value = val_str

def parse_ga4_query_string(raw_str):
    if not raw_str or not isinstance(raw_str, str): return {}
    if "?" in raw_str: raw_str = raw_str.split("?")[-1]
    params = {}
    for pair in raw_str.split("&"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            params[k] = urllib.parse.unquote(v)
    return params

def get_nested_value(d, path, separator="."):
    if not d or not isinstance(d, dict): return None
    keys = path.split(separator)
    current = d
    for key in keys:
        if isinstance(current, dict) and key in current: current = current[key]
        else: return None
    return current

def search_value_by_mappings(packet, m_row):
    if not packet or not isinstance(packet, dict): return None
    
    events = packet.get("xdm_payload", {}).get("events", [])
    if events:
        first_event = events[0]
        analytics_data = first_event.get("data", {}).get("__adobe", {}).get("analytics", {})
        
        if m_row["data_path"]:
            val = get_nested_value(first_event, m_row["data_path"])
            if val is not None: return val
            
        if m_row["xdm_path"]:
            p = m_row["xdm_path"]
            full_xdm_path = p if p.startswith("xdm.") else f"xdm.{p}"
            val = get_nested_value(first_event, full_xdm_path)
            if val is not None: return val
            
        if m_row["tool_name"] and m_row["tool_name"] in analytics_data:
            return analytics_data[m_row["tool_name"]]
            
        if m_row["aa_key"] and m_row["aa_key"] in analytics_data:
            return analytics_data[m_row["aa_key"]]
            
        xdm_data = first_event.get("xdm", {})
        check_key = m_row["aa_key"] or m_row["tool_name"]
        if check_key == "g" or check_key.lower() == "page url":
            return xdm_data.get("web", {}).get("webPageDetails", {}).get("URL", None)
        elif check_key == "r" or check_key.lower() == "referrer":
            return xdm_data.get("web", {}).get("webReferrer", {}).get("URL", None)
        elif check_key == "pageName" or check_key.lower() == "page name":
            return xdm_data.get("web", {}).get("webPageDetails", {}).get("name", None)
        elif check_key == "events":
            return analytics_data.get("events", xdm_data.get("eventType", None))

    params = packet.get("params", {})
    if params:
        check_key = m_row["aa_key"]
        if check_key and check_key in params:
            return params[check_key]

    return None

def format_extracted_value(val):
    if val is None: return ""
    if isinstance(val, (dict, list)): return json.dumps(val, ensure_ascii=False)
    return str(val)

def filter_events_by_type(events, target_type):
    filtered = []
    for ev in events:
        ev_type = ev.get("type", "")
        url_or_raw = ev.get("url", ev.get("raw", ""))
        
        is_ga4 = (ev_type == "GA4") or ("tid=G-" in url_or_raw) or ("google-analytics.com" in url_or_raw)
        is_aa = (ev_type in ["Adobe Analytics (Legacy)", "AEP Web SDK"]) or ("/b/ss/" in url_or_raw) or ("edge.adobedc.net" in url_or_raw)
        
        if target_type == "GA4" and is_ga4:
            filtered.append(ev)
        elif target_type == "AA" and is_aa:
            filtered.append(ev)
    return filtered

def group_events_by_step(events):
    """
    イベントを step_index をキーとした辞書にグループ化する（Phase 2 用）
    例: { 0: [event1, event2], 1: [event3] }
    """
    grouped = {}
    for ev in events:
        s_idx = ev.get("step_index", 0)
        if s_idx not in grouped:
            grouped[s_idx] = []
        grouped[s_idx].append(ev)
    return grouped

def process_single_sheet(ws, sheet_name, ev_new, ev_old, config, latest_filename, base_filename):
    ex_set = config["excel_setting"]
    ext_rules = config["extraction_rules"]
    replace_placeholders_in_sheet(ws, config)
    is_ga4 = (sheet_name == "GA4")
    
    START_DATA_COL = 1
    while ws.cell(row=2, column=START_DATA_COL).value:
        START_DATA_COL += 1

    mapping_rows = []
    url_row_idx = None
    for r in range(3, ws.max_row + 1):
        if START_DATA_COL == 4:
            aa_key = str(ws.cell(row=r, column=1).value or "").strip()
            tool_name = str(ws.cell(row=r, column=2).value or "").strip()
            desc = str(ws.cell(row=r, column=3).value or "").strip()
            xdm_path, data_path = "", ""
        else:
            aa_key = str(ws.cell(row=r, column=1).value or "").strip()
            xdm_path = str(ws.cell(row=r, column=2).value or "").strip()
            data_path = str(ws.cell(row=r, column=3).value or "").strip()
            tool_name = str(ws.cell(row=r, column=4).value or "").strip()
            desc = str(ws.cell(row=r, column=5).value or "").strip()
            
        if aa_key or tool_name:
            mapping_rows.append({
                "row_idx": r, "aa_key": aa_key, "tool_name": tool_name,
                "xdm_path": xdm_path, "data_path": data_path, "desc": desc
            })
            if not url_row_idx and (aa_key in ["g", "dl"] or "url" in tool_name.lower()):
                url_row_idx = r

    OLD_START_ROW = 2 + len(mapping_rows) + 4
    
    fills = {
        "new": PatternFill(start_color=ex_set["theme_color_new"], end_color=ex_set["theme_color_new"], fill_type="solid"),
        "old": PatternFill(start_color=ex_set["theme_color_old"], end_color=ex_set["theme_color_old"], fill_type="solid"),
        "diff": PatternFill(start_color=ex_set["diff_color"], end_color=ex_set["diff_color"], fill_type="solid"),
        "empty": PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
    }
    fonts = {
        "diff": Font(name=ex_set["font_name"], bold=True, color=ex_set["diff_font_color"], size=9),
        "normal": Font(name=ex_set["font_name"], size=9),
        "header": Font(name=ex_set["font_name"], bold=True, size=10)
    }
    thin_border = Border(left=Side(style='thin', color='CCCCCC'), right=Side(style='thin', color='CCCCCC'),
                         top=Side(style='thin', color='CCCCCC'), bottom=Side(style='thin', color='CCCCCC'))

    TITLE_COL = 4
    ws.cell(row=1, column=TITLE_COL, value=f"【 現在データ (新) 】 ファイル: {latest_filename}").font = Font(name=ex_set["font_name"], bold=True, size=11, color="2E6930")
    ws.cell(row=OLD_START_ROW - 1, column=TITLE_COL, value=f"【 過去データ (旧) 】 ファイル: {base_filename}").font = Font(name=ex_set["font_name"], bold=True, size=11, color="4B6F96")

    for idx, m_row in enumerate(mapping_rows):
        target_old_row = OLD_START_ROW + 1 + idx
        for col_i in range(1, START_DATA_COL):
            orig_val = ws.cell(row=m_row["row_idx"], column=col_i).value
            c_target = ws.cell(row=target_old_row, column=col_i, value=orig_val)
            c_target.font = fonts["normal"]
            c_target.fill = PatternFill(start_color="FAFAF7", end_color="FAFAF7", fill_type="solid")
            c_target.border = thin_border

    grouped_new = group_events_by_step(ev_new)
    grouped_old = group_events_by_step(ev_old)
    
    all_steps = sorted(set(list(grouped_new.keys()) + list(grouped_old.keys())))
    
    current_col = START_DATA_COL
    total_output_cols = 0
    
    for s_idx in all_steps:
        packets_new_for_step = grouped_new.get(s_idx, [])
        packets_old_for_step = grouped_old.get(s_idx, [])
        
        max_packets_in_step = max(len(packets_new_for_step), len(packets_old_for_step))
        if max_packets_in_step == 0: continue
        
        for p_idx, (p_new, p_old) in enumerate(zip_longest(packets_new_for_step, packets_old_for_step)):
            p_label = f"Step {s_idx + 1}"
            if max_packets_in_step > 1:
                p_label += f"-{p_idx + 1}"
                
            for cell_h, fill_h in [(ws.cell(row=2, column=current_col, value=p_label), fills["new"]),
                                   (ws.cell(row=OLD_START_ROW, column=current_col, value=p_label), fills["old"])]:
                cell_h.font = fonts["header"]
                cell_h.fill = fill_h
                cell_h.alignment = Alignment(horizontal="center", vertical="center")
                cell_h.border = thin_border

            if is_ga4:
                parsed_new = parse_ga4_query_string(p_new.get("raw", p_new.get("url", ""))) if p_new else {}
                parsed_old = parse_ga4_query_string(p_old.get("raw", p_old.get("url", ""))) if p_old else {}

            for idx, m_row in enumerate(mapping_rows):
                row_new = m_row["row_idx"]
                row_old = OLD_START_ROW + 1 + idx
                val_new = val_old = ""
                
                if is_ga4:
                    if p_new and m_row["aa_key"] in parsed_new: val_new = parsed_new[m_row["aa_key"]]
                    if p_old and m_row["aa_key"] in parsed_old: val_old = parsed_old[m_row["aa_key"]]
                else:
                    res_new = search_value_by_mappings(p_new, m_row)
                    res_old = search_value_by_mappings(p_old, m_row)
                    if res_new is not None: val_new = format_extracted_value(res_new)
                    if res_old is not None: val_old = format_extracted_value(res_old)

                c_new = ws.cell(row=row_new, column=current_col, value=val_new)
                c_old = ws.cell(row=row_old, column=current_col, value=val_old)
                
                for c in [c_new, c_old]:
                    c.font = fonts["normal"]
                    c.border = thin_border
                    c.alignment = Alignment(horizontal="left", vertical="center")

                is_ignored = m_row["aa_key"] in ext_rules["ignore_params"]

                if not p_new and p_old:
                    c_new.fill = fills["empty"]
                    c_new.value = "欠損"
                    if not is_ignored and val_old != "": c_old.fill = fills["diff"]
                elif p_new and not p_old:
                    if not is_ignored and val_new != "": c_new.fill = fills["diff"]
                    c_old.fill = fills["empty"]
                    c_old.value = "過去になし"
                elif val_new != val_old:
                    if not is_ignored:
                        if val_new != "": c_new.fill = fills["diff"]; c_new.font = fonts["diff"]
                        if val_old != "": c_old.fill = fills["diff"]

            current_col += 1
            total_output_cols += 1

    if total_output_cols == 0: return

    ws.row_dimensions.group(3, 2 + len(mapping_rows), hidden=False, outline_level=1)
    ws.row_dimensions.group(OLD_START_ROW + 1, OLD_START_ROW + len(mapping_rows), hidden=False, outline_level=1)

    for idx, m_row in enumerate(mapping_rows):
        row_new = m_row["row_idx"]
        row_old = OLD_START_ROW + 1 + idx
        is_empty_row = True
        
        for c_idx in range(total_output_cols):
            col_num = START_DATA_COL + c_idx
            v_new = str(ws.cell(row=row_new, column=col_num).value or "").strip()
            v_old = str(ws.cell(row=row_old, column=col_num).value or "").strip()
            
            if (v_new and v_new not in ["欠損", "過去になし"]) or \
               (v_old and v_old not in ["欠損", "過去になし"]):
                is_empty_row = False
                break
                
        if is_empty_row:
            ws.row_dimensions[row_new].hidden = True
            ws.row_dimensions[row_old].hidden = True

    if url_row_idx:
        start_col_grp = START_DATA_COL
        current_url = str(ws.cell(row=url_row_idx, column=START_DATA_COL).value or "").strip()
        
        for c_idx in range(1, total_output_cols):
            col_num = START_DATA_COL + c_idx
            url_val = str(ws.cell(row=url_row_idx, column=col_num).value or "").strip()
            
            if url_val != current_url:
                if col_num - 1 > start_col_grp:
                    for grp_col in range(start_col_grp + 1, col_num):
                        col_letter = get_column_letter(grp_col)
                        ws.column_dimensions[col_letter].outline_level = 1
                start_col_grp = col_num
                current_url = url_val
                
        if (START_DATA_COL + total_output_cols - 1) > start_col_grp:
            for grp_col in range(start_col_grp + 1, START_DATA_COL + total_output_cols):
                col_letter = get_column_letter(grp_col)
                ws.column_dimensions[col_letter].outline_level = 1

    ws.sheet_properties.outlinePr.summaryRight = False
    ws.sheet_properties.outlinePr.summaryBelow = False

    # 修正: D列(データ出力列)以降が非表示にならないよう、一番最後に強制的に表示状態に上書きする
    max_col_to_check = START_DATA_COL + total_output_cols - 1
    for c_idx in range(1, max_col_to_check + 1):
        col_letter = get_column_letter(c_idx)
        if c_idx < START_DATA_COL:
            # A, B, C 列は隠す
            ws.column_dimensions[col_letter].hidden = True
        else:
            # D列以降のデータ列は絶対に表示させる
            ws.column_dimensions[col_letter].hidden = False
            
            # 列幅の自動調整もここで行う
            max_len = 0
            for cell in ws[col_letter]:
                if cell.value:
                    max_len = max(max_len, len(str(cell.value)))
            ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 40)


def generate_compare_report(project_name, latest_json_path, base_json_path, output_excel_name, logger_func=print):
    project_dir = os.path.join("project", project_name)
    template_path = os.path.join(project_dir, "template.xlsx")
    
    l_path = latest_json_path if os.path.isabs(latest_json_path) else os.path.join(project_dir, "outputs", latest_json_path)
    b_path = base_json_path if os.path.isabs(base_json_path) else os.path.join(project_dir, "outputs", base_json_path)
    output_excel_path = os.path.join(project_dir, "outputs", output_excel_name)

    config = load_project_config(project_dir)
    
    if not os.path.exists(template_path): return logger_func(f"テンプレートが見つかりません: {template_path}")
    if not os.path.exists(l_path): return logger_func(f"最新の計測JSONが見つかりません: {l_path}")
    if not os.path.exists(b_path): return logger_func(f"比較元の計測JSONが見つかりません: {b_path}")

    try:
        with open(l_path, "r", encoding="utf-8") as f: latest_data = json.load(f)
        with open(b_path, "r", encoding="utf-8") as f: base_data = json.load(f)
    except json.JSONDecodeError:
        return logger_func("JSONファイルの読み込みに失敗しました。ファイルが壊れていないか確認してください。")

    latest_events = latest_data.get("events", [])
    base_events = base_data.get("events", [])
    
    # Phase 1: ツールごとに配列を分離
    ga4_new = filter_events_by_type(latest_events, "GA4")
    ga4_old = filter_events_by_type(base_events, "GA4")
    aa_new = filter_events_by_type(latest_events, "AA")
    aa_old = filter_events_by_type(base_events, "AA")

    wb = load_workbook(template_path)
    
    # どちらのシートを処理対象とするか決定（両方ある場合は両方処理）
    process_targets = []
    if ga4_new or ga4_old:
        if "GA4" in wb.sheetnames:
            process_targets.append(("GA4", ga4_new, ga4_old))
        else:
            logger_func("GA4のデータがありますが、テンプレートに『GA4』シートが無いためスキップします。")
            
    if aa_new or aa_old:
        if "Adobe Analytics" in wb.sheetnames:
            process_targets.append(("Adobe Analytics", aa_new, aa_old))
        else:
            logger_func("Adobeのデータがありますが、テンプレートに『Adobe Analytics』シートが無いためスキップします。")

    if not process_targets:
        return logger_func("処理対象のデータに対応するシートが見つかりません。テンプレートのシート名（GA4 / Adobe Analytics）を確認してください。")

    keep_sheets = ["表紙"] + [t[0] for t in process_targets]
    for name in list(wb.sheetnames):
        if name not in keep_sheets:
            wb.remove(wb[name])

    if "表紙" in wb.sheetnames:
        replace_placeholders_in_sheet(wb["表紙"], config)

    # ターゲットとなるシート（最大2シート）を順番に処理
    for sheet_name, ev_new, ev_old in process_targets:
        logger_func(f"シート『{sheet_name}』の比較処理を行っています。")
        process_single_sheet(
            ws=wb[sheet_name],
            sheet_name=sheet_name,
            ev_new=ev_new,
            ev_old=ev_old,
            config=config,
            latest_filename=os.path.basename(latest_json_path),
            base_filename=os.path.basename(base_json_path)
        )

    try:
        wb.save(output_excel_path)
    except PermissionError:
        logger_func(f"【エラー】出力先のExcelファイル ({output_excel_name}) が開かれています。\nExcelを閉じてから再度実行してください。\n")
        return None

    logger_func(f"比較レポートを生成しました。\n保存先: {output_excel_path}\n")
    return output_excel_path

if __name__ == "__main__":
    if len(sys.argv) > 4:
        generate_compare_report(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        print("使い方: python excel_reporter.py [案件名] [最新JSON名] [過去JSON名] [出力Excel名]")
