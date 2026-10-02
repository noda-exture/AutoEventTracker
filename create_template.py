import os
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side

def create_comprehensive_template(template_path=None):
    template_path = template_path or os.path.join("project", "template.xlsx")
    os.makedirs(os.path.dirname(os.path.abspath(template_path)), exist_ok=True)
    
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
    
    # A列はAppMeasurementの送信キー、B/C列はWeb SDKの抽出パス。
    aa_headers = ["AppMeasurement", "WebSDK(XDM)", "WebSDK(Data)", "項目", "説明"]
    for col_idx, text in enumerate(aa_headers, 1):
        cell = ws_aa.cell(row=2, column=col_idx, value=text)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    
    # Adobe公式: query-parameters / xdm-var-mapping / data-var-mapping。
    # 直接対応のない項目は空欄。XDMの複合情報は別行で比較する。
    aa_defs = [
        ("g", "web.webPageDetails.URL", "data.__adobe.analytics.pageURL", "Page URL", "計測対象ページのURL。AppMeasurementでは長いURLの続きは-gに入る"),
        ("-g", "", "", "Page URL Overflow", "AppMeasurementで255バイトを超えたURLの続き"),
        ("pageName", "web.webPageDetails.name", "data.__adobe.analytics.pageName", "Page Name", "ページ名"),
        ("pageType", "web.webPageDetails.isErrorPage", "data.__adobe.analytics.pageType", "Page Type", "エラーページ。AppMeasurement/DataはerrorPage、XDMは真偽値（未変換）"),
        ("ch", "web.webPageDetails.siteSection", "data.__adobe.analytics.channel", "Channel", "サイトセクション / チャネル"),
        ("r", "web.webReferrer.URL", "data.__adobe.analytics.referrer", "Referrer", "参照元URL"),
        ("server", "web.webPageDetails.server", "data.__adobe.analytics.server", "Server", "サーバー名・論理サーバー名"),
        ("v0", "marketing.trackingCode", "data.__adobe.analytics.campaign", "Campaign", "キャンペーンID（tracking code）"),
        ("pe", "web.webInteraction.type", "data.__adobe.analytics.linkType", "Link Type", "AppMeasurement: lnk_o/lnk_d/lnk_e、Data: o/d/e、XDM: other/download/exit（未変換）"),
        ("pev2", "web.webInteraction.name", "data.__adobe.analytics.linkName", "Link Name", "クリックされたリンクの名称"),
        ("pev1", "web.webInteraction.URL", "data.__adobe.analytics.linkURL", "Link URL", "クリックされたリンクのURL"),
        ("events", "", "data.__adobe.analytics.events", "Events", "イベント一覧。XDMのcommerceやカスタムイベントとは別行で確認"),
        ("products", "", "data.__adobe.analytics.products", "Products", "商品文字列（カテゴリ;商品;数量;金額;イベント;eVar）。XDM商品配列は別行"),
        ("purchaseID", "commerce.order.purchaseID", "data.__adobe.analytics.purchaseID", "Purchase ID", "購入の重複排除に使用するID"),
        ("xact", "commerce.order.payments[0].transactionID", "data.__adobe.analytics.transactionID", "Transaction ID", "Data Sourcesでオンライン・オフライン情報を結び付けるID"),
        ("cc", "commerce.order.currencyCode", "data.__adobe.analytics.currencyCode", "Currency Code", "通貨コード（例: JPY、USD）"),
        ("mid", "identityMap.ECID[0].id", "", "Experience Cloud ID", "Experience Cloudの訪問者識別子（ECID）"),
        ("aid", "", "", "Analytics Visitor ID", "従来のAnalytics訪問者ID（s_vi）。現在は主にECIDを使用"),
        ("fid", "", "", "Fallback Visitor ID", "代替の訪問者ID（s_fid）"),
        ("vid", "", "", "Visitor ID Override", "visitorIDで明示的に設定した訪問者ID"),
        ("mcorgid", "", "", "Organization ID", "Experience Cloud組織ID"),
        ("aamlh", "", "", "Audience Manager Region", "Audience Managerの地域ヒント"),
        ("aamb", "", "", "Audience Manager Blob", "ID同期に利用するエンコード済みデータ"),
        ("sdid", "", "", "Supplemental Data ID", "AnalyticsとTargetなどのヒットを関連付けるID"),
        ("t", "", "", "Generated Time", "AppMeasurementが生成した日時・曜日・時差。月は0始まり"),
        ("ts", "", "", "Timestamp", "明示的に指定したヒットのタイムスタンプ"),
        ("ce", "", "", "Character Set", "文字コード（charSet）"),
        ("cl", "", "", "Cookie Lifetime", "Cookieの有効期間設定"),
        ("k", "environment.browserDetails.cookiesEnabled", "data.__adobe.analytics.cookiesEnabled", "Cookie Support", "Cookieの利用可否"),
        ("s", "", "data.__adobe.analytics.resolution", "Screen Resolution", "画面解像度。XDMは幅・高さを別行で確認"),
        ("c", "device.colorDepth", "data.__adobe.analytics.colorDepth", "Color Depth", "画面の色深度"),
        ("bw", "environment.browserDetails.viewportWidth", "data.__adobe.analytics.browserWidth", "Browser Width", "ブラウザ表示領域の幅"),
        ("bh", "environment.browserDetails.viewportHeight", "data.__adobe.analytics.browserHeight", "Browser Height", "ブラウザ表示領域の高さ"),
        ("ct", "environment.connectionType", "data.__adobe.analytics.connectionType", "Connection Type", "ネットワーク接続種別"),
        ("v", "environment.browserDetails.javaEnabled", "data.__adobe.analytics.javaEnabled", "Java Enabled", "Javaの有効状態。JavaScriptとは別"),
        ("zip", "placeContext.geo.postalCode", "data.__adobe.analytics.zip", "Zip Code", "明示的に送信した郵便番号"),
        ("cp", "", "", "Customer Perspective", "ヒット種別に関連する値（customerPerspective）"),
        ("D", "", "data.__adobe.analytics.dynamicVariablePrefix", "Dynamic Variable Prefix", "動的変数の接頭辞"),
        ("ndh", "", "", "AppMeasurement Flag", "AppMeasurementが付与する内部フラグ"),
        ("pf", "", "", "Platform Flag", "Adobe内部のプラットフォームフラグ"),
        ("lrt", "", "", "Last Request Timing", "前回リクエストの往復時間（ミリ秒）"),
        ("AQB", "", "", "Request Start", "送信クエリの開始マーカー"),
        ("AQE", "", "", "Request End", "送信クエリの終了マーカー"),
        ("tnta", "", "", "Analytics for Target", "Analytics for Target連携のペイロード"),
        ("tnt", "", "", "Target Payload", "Target連携のペイロード（pe=tnt）"),
        ("", "eventType", "", "XDM Event Type", "Web SDKのイベント種別。Analyticsのevents一覧とは異なる"),
        ("", "timestamp", "", "XDM Timestamp", "Web SDKイベントの日時"),
        ("", "productListItems", "", "XDM Product Items", "XDMの商品配列。商品ID・名称・数量・金額などを配列のまま確認"),
        ("", "device.screenWidth", "", "XDM Screen Width", "XDMの画面幅"),
        ("", "device.screenHeight", "", "XDM Screen Height", "XDMの画面高さ"),
        ("", "environment.browserDetails.acceptLanguage", "", "XDM Language", "ブラウザ言語。AppMeasurementではHTTPヘッダーのためA列は空欄"),
        ("", "environment.browserDetails.userAgent", "", "XDM User Agent", "User-Agent。AppMeasurementではHTTPヘッダーのためA列は空欄"),
        ("", "", "data.__adobe.analytics.contextData", "Context Data (Data)", "Web SDK Dataのコンテキストデータ全体。キーの意味は案件ごとに設定"),
    ]
    for field, event, label in [
        ("productViews", "prodView", "Product Views"),
        ("productListOpens", "scOpen", "Cart Opens"),
        ("productListAdds", "scAdd", "Cart Additions"),
        ("productListRemovals", "scRemove", "Cart Removals"),
        ("productListViews", "scView", "Cart Views"),
        ("checkouts", "scCheckout", "Checkouts"),
        ("purchases", "purchase", "Purchases"),
    ]:
        aa_defs.append(("", f"commerce.{field}.value", "", f"XDM {label}",
                        f"XDMの標準コマース指標。AppMeasurement/Dataではevents内の{event}に相当"))
    for i in range(1, 4):
        aa_defs.append((f"l{i}", f"_experience.analytics.customDimensions.lists.list{i}.list",
                        f"data.__adobe.analytics.list{i}", f"list{i}",
                        "リスト変数。意味・区切り文字は案件で設定。XDMは配列のまま確認"))
    for i in range(1, 76):
        aa_defs.append((f"c{i}", f"_experience.analytics.customDimensions.props.prop{i}",
                        f"data.__adobe.analytics.prop{i}", f"prop{i}", "カスタムトラフィック変数。意味は案件で設定"))
    for i in range(1, 251):
        aa_defs.append((f"v{i}", f"_experience.analytics.customDimensions.eVars.eVar{i}",
                        f"data.__adobe.analytics.eVar{i}", f"eVar{i}", "カスタムコンバージョン変数。意味は案件で設定"))

    ws_aa.merge_cells("A1:E1")
    ws_aa['A1'] = "Adobe公式のWeb計測項目。各方式の送信値を比較します。空欄の対応・案件別設定は表紙を参照。"
    ws_aa['A1'].font = body_font
    ws_aa.freeze_panes = "A3"
    ws_aa.row_dimensions[2].height = 25
    
    for idx, row_data in enumerate(aa_defs):
        for col_idx, val in enumerate(row_data, 1):
            cell = ws_aa.cell(row=3+idx, column=col_idx, value=val)
            cell.font = body_font
            cell.border = thin_border
            cell.alignment = Alignment(wrap_text=True, vertical="center")
        ws_aa.row_dimensions[3+idx].height = 48

    # ─── ③ 【GA4】 ───
    ws_ga4 = wb.create_sheet(title="GA4")
    ws_ga4.views.sheetView[0].showGridLines = True
    
    # GA4側もプレフィックスを外し、D列・E列の名称を統一
    ga4_headers = ["GA4パラメータ", "パラメータ種別", "データ型", "項目", "説明"]
    for col_idx, text in enumerate(ga4_headers, 1):
        cell = ws_ga4.cell(row=2, column=col_idx, value=text)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    
    ws_ga4.row_dimensions[2].height = 25
    
    # Webの /g/collect 用。送信の有無・値は環境や設定で異なる。
    # データ型は値の意味を示すメタデータであり、抽出値を数値に変換しない。
    # 公開仕様で意味を確定できない内部キーは、加工せず比較するために定義する。
    ga4_definitions = [
        ("v", "基本項目", "数値", "Protocol Version", "送信プロトコルのバージョン（送信例: 2）"),
        ("tid", "基本項目", "文字列", "Measurement ID", "送信先の測定ID（G-で始まるID）"),
        ("en", "基本項目", "文字列", "Event Name", "発生したイベント名（例: page_view、purchase）"),
        ("dl", "基本項目", "文字列", "Page URL", "計測対象ページのフルURL"),
        ("dt", "基本項目", "文字列", "Page Title", "計測対象ページのタイトル"),
        ("dr", "基本項目", "文字列", "Referrer", "参照元URL"),
        ("cid", "基本項目", "文字列", "Client ID", "クライアント識別子。小数として扱わず文字列を保持"),
        ("sid", "基本項目", "文字列", "Session ID", "セッション識別子。識別子として文字列を保持"),
        ("sct", "基本項目", "数値", "Session Count", "セッション数"),
        ("seg", "基本項目", "フラグ", "Session Engagement", "セッションのエンゲージメントを示すフラグ"),
        ("ul", "基本項目", "文字列", "Language", "ブラウザの言語（送信例: ja）"),
        ("sr", "基本項目", "文字列", "Screen Resolution", "画面解像度（幅x高さ）"),
        ("uaa", "基本項目", "文字列", "UA Architecture", "User-AgentのCPUアーキテクチャ（送信例: arm）"),
        ("uab", "基本項目", "文字列", "UA Bitness", "User-Agentのビット数（送信例: 64）"),
        ("uafvl", "基本項目", "文字列", "UA Full Version List", "ブラウザのブランドとバージョンの一覧"),
        ("uam", "基本項目", "文字列", "UA Model", "端末モデル。空文字の場合もある"),
        ("uamb", "基本項目", "フラグ", "UA Mobile", "モバイル端末を示すUser-Agentフラグ"),
        ("uap", "基本項目", "文字列", "UA Platform", "OS・プラットフォーム名（送信例: macOS）"),
        ("uapv", "基本項目", "文字列", "UA Platform Version", "OS・プラットフォームのバージョン"),
        ("uaw", "基本項目", "フラグ", "UA WoW64", "User-AgentのWoW64フラグ"),
        ("gcd", "基本項目", "文字列", "Consent Signals", "同意状態に関するエンコード値。送信値のまま比較"),
        ("npa", "基本項目", "フラグ", "Non-personalized Ads", "広告パーソナライズの制限に関するフラグ"),
        ("dma", "基本項目", "文字列", "DMA Signal", "同意モードに関連する送信値。送信値のまま比較"),
        ("gtm", "基本項目", "文字列", "Google Tag Metadata", "Googleタグの内部メタデータ。GTMコンテナIDとは別の値"),
        ("_p", "基本項目", "文字列", "Internal _p", "Googleタグの内部パラメータ。実行ごとに変動し得る値"),
        ("_s", "基本項目", "数値", "Internal _s", "Googleタグの内部パラメータ。送信例: 1"),
        ("_eu", "基本項目", "文字列", "Internal _eu", "Googleタグの内部パラメータ。意味は断定せず送信値を比較"),
        ("frm", "基本項目", "文字列", "Internal frm", "Googleタグの内部パラメータ。送信例: 0"),
        ("pscdl", "基本項目", "文字列", "Internal pscdl", "Googleタグの内部パラメータ。送信例: noapi"),
        ("rcb", "基本項目", "文字列", "Internal rcb", "Googleタグの内部パラメータ。送信例: 10 / 11"),
        ("gaf", "基本項目", "文字列", "Internal gaf", "Googleタグの内部パラメータ。一部の送信例のみ存在"),
        ("ngs", "基本項目", "文字列", "Internal ngs", "Googleタグの内部パラメータ。一部の送信例のみ存在"),
        ("tag_exp", "基本項目", "文字列", "Internal tag_exp", "Googleタグの内部パラメータ。複数の値を含む文字列を保持"),
        ("tfd", "基本項目", "数値", "Internal tfd", "Googleタグの内部パラメータ。実行ごとに変動し得る値"),
    ]

    ga4_definitions.extend([
        ("uid", "基本項目", "文字列", "User ID", "サイトで設定したUser-ID。未設定の場合は送信されない"),
        ("_et", "基本項目", "数値", "Engagement Time", "エンゲージメント時間（ミリ秒）"),
        ("_ss", "基本項目", "フラグ", "Session Start", "セッション開始フラグ"),
        ("_fv", "基本項目", "フラグ", "First Visit", "初回訪問フラグ"),
        ("_nsi", "基本項目", "フラグ", "New Session", "Googleタグのセッション関連内部フラグ"),
        ("_dbg", "基本項目", "フラグ", "Debug Mode", "デバッグモードのフラグ"),
        ("gcs", "基本項目", "文字列", "Consent State", "同意状態のエンコード値"),
        ("dma_cps", "基本項目", "文字列", "DMA Consent Services", "Googleサービスへの同意に関連する送信値"),
        ("gcu", "基本項目", "文字列", "Consent Update", "同意更新に関連する送信値"),
        ("are", "基本項目", "文字列", "Internal are", "Googleタグの内部パラメータ。送信値のまま比較"),
        ("ir", "基本項目", "文字列", "Internal ir", "Googleタグの内部パラメータ。送信値のまま比較"),
        ("gclid", "基本項目", "文字列", "Google Click ID", "広告クリックID。URL内にのみ含まれる場合もある"),
        ("dclid", "基本項目", "文字列", "DoubleClick Click ID", "広告クリックID。URL内にのみ含まれる場合もある"),
        ("srsltid", "基本項目", "文字列", "Merchant Click ID", "Merchant Center関連のクリックID"),
        ("ci", "基本項目", "文字列", "Campaign ID", "キャンペーンID"),
        ("cn", "基本項目", "文字列", "Campaign Name", "キャンペーン名"),
        ("cs", "基本項目", "文字列", "Campaign Source", "キャンペーンの参照元"),
        ("cm", "基本項目", "文字列", "Campaign Medium", "キャンペーンのメディア"),
        ("ck", "基本項目", "文字列", "Campaign Term", "キャンペーンのキーワード"),
        ("cc", "基本項目", "文字列", "Campaign Content", "キャンペーンのコンテンツ"),
        ("cu", "基本項目", "文字列", "Currency", "通貨コード（例: JPY、USD）"),
    ])

    # 標準イベントのパラメータも ep. / epn. で送信される。
    # 参考: https://support.google.com/analytics/answer/9216061
    #       https://developers.google.com/analytics/devguides/collection/ga4/reference/events
    standard_strings = [
        ("link_url", "リンク先URL"), ("link_domain", "リンク先ドメイン"),
        ("link_id", "リンク要素のID"), ("link_classes", "リンク要素のCSSクラス"),
        ("link_text", "リンクの表示テキスト"), ("outbound", "外部リンクかを示す値"),
        ("file_name", "ダウンロードファイル名"), ("file_extension", "ファイルの拡張子"),
        ("search_term", "サイト内検索キーワード"),
        ("video_provider", "動画の提供元"), ("video_title", "動画タイトル"),
        ("video_url", "動画URL"), ("visible", "動画の表示状態"),
        ("form_id", "フォームのID"), ("form_name", "フォーム名"),
        ("form_destination", "フォームの送信先"),
        ("form_submit_text", "送信ボタンのテキスト"),
        ("form_first_field_id", "最初に操作したフィールドのID"),
        ("form_first_field_name", "最初に操作したフィールド名"),
        ("form_first_field_type", "最初に操作したフィールド種別"),
        ("method", "ログイン・登録・共有の方法"),
        ("content_type", "コンテンツの種別"), ("content_id", "コンテンツのID"),
        ("item_id", "共有されたコンテンツなどのID（イベント単位）"),
        ("item_name", "アイテム名（イベント単位）"), ("group_id", "グループID"),
        ("transaction_id", "購入・返金の取引ID"), ("affiliation", "店舗・所属名"),
        ("coupon", "クーポンコード（イベント単位）"),
        ("payment_type", "支払い方法"), ("shipping_tier", "配送方法"),
        ("item_list_id", "商品リストID（イベント単位）"),
        ("item_list_name", "商品リスト名（イベント単位）"),
        ("promotion_id", "プロモーションID（イベント単位）"),
        ("promotion_name", "プロモーション名（イベント単位）"),
        ("creative_name", "クリエイティブ名（イベント単位）"),
        ("creative_slot", "クリエイティブ掲載枠（イベント単位）"),
        ("lead_source", "見込み顧客の獲得元"),
        ("lead_status", "見込み顧客の状態"),
        ("unconvert_lead_reason", "見込み顧客が成約しなかった理由"),
        ("disqualified_lead_reason", "見込み顧客を対象外とした理由"),
        ("virtual_currency_name", "仮想通貨名"), ("level_name", "ゲームのレベル名"),
        ("character", "ゲームのキャラクター"), ("achievement_id", "実績のID"),
    ]
    standard_numbers = [
        ("percent_scrolled", "スクロール到達率（%）"),
        ("video_current_time", "動画の再生位置（秒）"),
        ("video_duration", "動画の長さ（秒）"), ("video_percent", "動画の再生率（%）"),
        ("form_length", "フォームのフィールド数"),
        ("form_first_field_position", "最初に操作したフィールドの位置"),
        ("value", "イベントの金額・価値"), ("tax", "税額"), ("shipping", "送料"),
        ("engagement_time_msec", "明示的に送信したエンゲージメント時間（ミリ秒）。通常は_etも確認"),
        ("score", "ゲームのスコア"), ("level", "ゲームのレベル"),
        ("success", "成功したかを示す値"),
    ]
    for name, description in standard_strings:
        ga4_definitions.append((f"ep.{name}", "標準イベントパラメータ", "文字列", name, description))
    for name, description in standard_numbers:
        # 実装による文字列送信も別行で確認する。完全一致の既存抽出処理に対応。
        for prefix, data_type in (("epn", "数値"), ("ep", "文字列")):
            ga4_definitions.append((f"{prefix}.{name}", "標準イベントパラメータ", data_type, name, description))

    # items配列は /g/collect ではpr1、pr2…に圧縮される。
    # 現行アダプタは完全一致抽出のため、商品ごとの送信文字列を比較する。
    for number in range(1, 201):
        ga4_definitions.append((f"pr{number}", "商品データ", "文字列", f"Item {number}",
                                f"商品{number}の送信文字列（ID・商品名・価格・数量など）。内訳の分解は行わない"))

    # サイト独自のep./epn./up./upn.は初期定義に含めない。
    # 利用者が案件別template.xlsxのGA4末尾に実際の送信キーを追加する。
    ws_ga4.cell(row=1, column=1, value="汎用Web GA4。サイト別項目の追加方法は表紙を参照。未送信項目は空欄。")
    ws_ga4.merge_cells("A1:E1")
    ws_ga4['A1'].font = body_font
    ws_ga4.freeze_panes = "A3"
    
    for idx, row_data in enumerate(ga4_definitions):
        row_idx = 3 + idx
        for col_idx, val in enumerate(row_data, 1):
            cell = ws_ga4.cell(row=row_idx, column=col_idx, value=val)
            cell.font = body_font
            cell.border = thin_border
            cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        ws_ga4.row_dimensions[row_idx].height = 44
            
            # 種別ごとのパステル色分け
        for col_idx, val in enumerate(row_data, 1):
            cell = ws_ga4.cell(row=row_idx, column=col_idx)
            if col_idx == 2:
                if val == "基本項目": cell.fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
                elif "イベントパラメータ" in val: cell.fill = PatternFill(start_color="E6F0FA", end_color="E6F0FA", fill_type="solid")
                elif "ユーザープロパティ" in val: cell.fill = PatternFill(start_color="F0E6FA", end_color="F0E6FA", fill_type="solid")

    # 列幅の最適化
    ws_aa.column_dimensions['A'].width = 16
    ws_aa.column_dimensions['B'].width = 48
    ws_aa.column_dimensions['C'].width = 43
    ws_aa.column_dimensions['D'].width = 26
    ws_aa.column_dimensions['E'].width = 65

    ws_ga4.column_dimensions['A'].width = 32
    ws_ga4.column_dimensions['B'].width = 24
    ws_ga4.column_dimensions['C'].width = 12
    ws_ga4.column_dimensions['D'].width = 32
    ws_ga4.column_dimensions['E'].width = 65

    ga4_notes = [
        "GA4テンプレートの使い方",
        "対象はWebの /g/collect 通信。基本項目、標準イベント項目、商品データを定義しています。",
        "送信項目はイベント・同意状態・実装により異なります。すべての行が送信必須という意味ではありません。",
        "案件別template.xlsxのGA4シート末尾に行を追加し、A～E列を既存行と同じ形式で記入してください。",
        "A列には実際の送信キーを記入します。ep.は文字列イベント項目、epn.は数値イベント項目です。",
        "ユーザープロパティはup.が文字列、upn.が数値です。GA4画面の表示名ではなく送信キーを指定してください。",
        "サイト独自のカスタム項目は初期定義に含めていません。標準項目でもep.で送られるものがあります。",
        "pr1～pr200は商品ごとの送信文字列を比較します。商品ID・価格などの個別展開は行いません。",
        "数値項目のepn.とep.は別行です。実際に送信された型の行に値が入ります。不要な行は削除できます。",
        "内部パラメータは変更される場合があります。未定義キーは案件ごとに追加してください。",
        "標準イベント: https://developers.google.com/analytics/devguides/collection/ga4/reference/events",
        "拡張計測: https://support.google.com/analytics/answer/9216061",
    ]
    for row, note in enumerate(ga4_notes, 8):
        ws_top.merge_cells(start_row=row, start_column=2, end_row=row, end_column=10)
        ws_top.cell(row=row, column=2, value=note).font = body_font
        ws_top.cell(row=row, column=2).alignment = Alignment(wrap_text=True, vertical="center")
        ws_top.row_dimensions[row].height = 42

    aa_notes = [
        "Adobe Analyticsテンプレートの使い方",
        "A列はAppMeasurementのクエリキー、B列はxdm内のパス、C列はdataから始まるパスです。",
        "直接対応する値がない列は空欄です。未送信は欠落とは限りません。ヘッダー・URLパス内の情報は別途確認してください。",
        "リンク種別・エラーページ・商品情報は方式間で形式が異なります。値の正規化やAdobe側の集計は再現しません。",
        "prop1～75、eVar1～250、list1～3は設定用の枠です。各サイトの設計に合わせて項目名・説明を記入してください。",
        "独自XDMを使用する場合はB列を実際のパスに変更してください。初期値はAdobe公式のAnalytics用XDMです。",
        "XDMのカスタムイベントは案件ごとに行を追加します。例: _experience.analytics.event1to100.event1.value",
        "events一覧、XDM eventType、XDMコマース指標は別行で確認します。商品文字列とXDM商品配列も別行です。",
        "AppMeasurementのコンテキストデータは送信形式が階層化されます。任意のキーを追加する前に保存データを確認してください。",
        "DataとXDMが両方ある場合はDataを優先します。Dataの標準名と短縮名の同時指定は避けてください。",
        "Adobe送信キー: https://experienceleague.adobe.com/en/docs/analytics/implementation/validate/query-parameters",
        "Adobe XDM対応: https://experienceleague.adobe.com/en/docs/analytics/implementation/aep-edge/xdm-var-mapping",
        "Adobe Data対応: https://experienceleague.adobe.com/en/docs/analytics/implementation/aep-edge/data-var-mapping",
    ]
    for row, note in enumerate(aa_notes, 22):
        ws_top.merge_cells(start_row=row, start_column=2, end_row=row, end_column=10)
        ws_top.cell(row=row, column=2, value=note).font = body_font
        ws_top.cell(row=row, column=2).alignment = Alignment(wrap_text=True, vertical="center")
        ws_top.row_dimensions[row].height = 48
    
    wb.save(template_path)
    print(f"汎用マスターテンプレートを生成しました: {template_path}")
    return template_path

if __name__ == "__main__":
    create_comprehensive_template()
