import os
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side

def create_comprehensive_template():
    project_dir = os.path.join("project", "sonysonpo")
    os.makedirs(project_dir, exist_ok=True)
    template_path = os.path.join(project_dir, "template.xlsx")
    
    wb = Workbook()
    
    # ─── ① 【表紙】 ───
    ws_top = wb.active
    ws_top.title = "表紙"
    ws_top.views.sheetView[0].showGridLines = True
    
    ws_top.cell(row=2, column=2, value="{client_name} 御中").font = Font(name="游ゴシック", size=14, bold=True)
    ws_top.cell(row=3, column=2, value="{task_name}").font = Font(name="游ゴシック", size=18, bold=True, color="1F497D")
    ws_top.cell(row=5, column=2, value="検証実施日: {date}").font = Font(name="游ゴシック", size=11)
    
    # 共通スタイル定義
    header_fill = PatternFill(start_color="333333", end_color="333333", fill_type="solid")
    header_font = Font(name="游ゴシック", size=10, bold=True, color="FFFFFF")
    body_font = Font(name="游ゴシック", size=10)
    thin_side = Side(style='thin', color='CCCCCC')
    thin_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

    # ─── ② 【Adobe Analytics】 ───
    ws_aa = wb.create_sheet(title="Adobe Analytics")
    ws_aa.views.sheetView[0].showGridLines = True
    
    # 💡 ご指定のスタイリッシュなヘッダー名に変更
    aa_headers = ["AppMeasurement", "WebSDK(XDM)", "WebSDK(Data)", "項目", "説明"]
    for col_idx, text in enumerate(aa_headers, 1):
        cell = ws_aa.cell(row=2, column=col_idx, value=text)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    
    aa_defs = [
        ("g", "web.webPageDetails.URL", "data.__adobe.analytics.g", "Page URL", "計測対象ページのURL"),
        ("pageName", "web.webPageDetails.name", "data.__adobe.analytics.pageName", "Page Name", "ページ名"),
        ("ch", "web.webPageDetails.siteSection", "data.__adobe.analytics.ch", "Channel", "サイトセクション / チャネル"),
        ("r", "web.webReferrer.URL", "data.__adobe.analytics.r", "Referrer", "前画面のURL（遷移元）"),
        ("server", "web.webPageDetails.server", "data.__adobe.analytics.server", "Server", "サーバー名"),
        ("v0", "marketing.trackingCode", "data.__adobe.analytics.campaign", "Campaign", "キャンペーンID（tracking code）"),
        ("pe", "web.webInteraction.name", "data.__adobe.analytics.pe", "Link name", "クリックされたリンクの名称"),
        ("pev2", "web.webInteraction.type", "data.__adobe.analytics.pev2", "Link type", "リンクの種別（d:DL, e:外部リンク, o:カスタム）"),
        ("pev1", "web.webInteraction.URL", "data.__adobe.analytics.pev1", "Link URL", "リンクの遷移先URL"),
        ("purchaseID", "commerce.order.purchaseID", "data.__adobe.analytics.purchaseID", "Purchase ID", "購買・申込のユニークID"),
        ("products", "productListItems", "data.__adobe.analytics.products", "Product", "製品・契約情報の文字列"),
        ("events", "commerce.purchases", "data.__adobe.analytics.events", "sevents", "発火したイベント一覧（events）")
    ]
    for i in range(1, 76): aa_defs.append((f"c{i}", f"_tenant.custom.prop{i}", f"data.__adobe.analytics.prop{i}", f"prop{i}", ""))
    for i in range(1, 256): aa_defs.append((f"v{i}", f"_tenant.custom.eVar{i}", f"data.__adobe.analytics.eVar{i}", f"eVar{i}", ""))
    
    for idx, row_data in enumerate(aa_defs):
        for col_idx, val in enumerate(row_data, 1):
            cell = ws_aa.cell(row=3+idx, column=col_idx, value=val)
            cell.font = body_font
            cell.border = thin_border

    # ─── ③ 【GA4】 ───
    ws_ga4 = wb.create_sheet(title="GA4")
    ws_ga4.views.sheetView[0].showGridLines = True
    
    # 💡 GA4側もプレフィックスを外し、D列・E列の名称を統一
    ga4_headers = ["GA4パラメータ", "パラメータ種別", "データ型", "項目", "説明"]
    for col_idx, text in enumerate(ga4_headers, 1):
        cell = ws_ga4.cell(row=2, column=col_idx, value=text)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    
    ws_ga4.row_dimensions[2].height = 25
    
    ga4_definitions = [
        ("en", "基本項目", "文字列", "Event Name", "発生したイベント名（例: page_view）"),
        ("dl", "基本項目", "文字列", "Page URL", "現在表示している画面のフルURL（dl）"),
        ("dt", "基本項目", "文字列", "Page Title", "画面のタイトル（dt）"),
        ("dr", "基本項目", "文字列", "Referrer", "1つ前にいた画面のURL（dr）"),
        ("cid", "基本項目", "文字列", "Client ID", "ブラウザ単位のユニークユーザーID（cid）"),
        ("sid", "基本項目", "数値", "Session ID", "セッションを識別する一意の数字（sid）"),
        ("ep.custom_link_url", "イベントパラメータ", "文字列", "Link URL", "クリックされたリンクのURL"),
        ("ep.custom_link_text", "イベントパラメータ", "文字列", "Link Text", "クリックされたボタンやリンクの文言"),
        ("ep.premium_amount", "イベントパラメータ", "文字列", "Premium Amount", "自動車保険の見積もり保険料"),
        ("up.user_status", "ユーザープロパティ", "文字列", "User Status", "ユーザーのログイン状態（up.）"),
        ("up.car_type", "ユーザープロパティ", "文字列", "Car Type", "ユーザーの所有車両区分（up.）")
    ]
    
    for idx, row_data in enumerate(ga4_definitions):
        row_idx = 3 + idx
        for col_idx, val in enumerate(row_data, 1):
            cell = ws_ga4.cell(row=row_idx, column=col_idx, value=val)
            cell.font = body_font
            cell.border = thin_border
            cell.alignment = Alignment(horizontal="left", vertical="center")
            
            # 種別ごとのパステル色分け
            if col_idx == 2:
                if val == "基本項目": cell.fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
                elif "イベントパラメータ" in val: cell.fill = PatternFill(start_color="E6F0FA", end_color="E6F0FA", fill_type="solid")
                elif "ユーザープロパティ" in val: cell.fill = PatternFill(start_color="F0E6FA", end_color="F0E6FA", fill_type="solid")

    # 列幅の最適化
    ws_aa.column_dimensions['A'].width = 16
    ws_aa.column_dimensions['B'].width = 32
    ws_aa.column_dimensions['C'].width = 35
    ws_aa.column_dimensions['D'].width = 18
    ws_aa.column_dimensions['E'].width = 35

    ws_ga4.column_dimensions['A'].width = 22
    ws_ga4.column_dimensions['B'].width = 24
    ws_ga4.column_dimensions['C'].width = 12
    ws_ga4.column_dimensions['D'].width = 22
    ws_ga4.column_dimensions['E'].width = 45
    
    wb.save(template_path)
    print(f"🎉 ヘッダー名称をスッキリと更新したマスターテンプレートを生成しました！")

if __name__ == "__main__":
    create_comprehensive_template()