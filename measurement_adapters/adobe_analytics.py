import re
import urllib.parse

from .base import MeasurementAdapter


def collect_legacy_params(packet):
    """Merge query and form body for display; retain repeated and blank values."""
    if packet.get('type') == 'AEP Web SDK' or 'xdm_payload' in packet:
        return dict(packet.get('params', {}))
    def parse(value):
        return {key: values[0] if len(values) == 1 else values
                for key, values in urllib.parse.parse_qs(value, keep_blank_values=True).items()}

    params = parse(urllib.parse.urlsplit(packet.get('url', '')).query)
    params.update(packet.get('params', {}))
    body = packet.get('post_data')
    if isinstance(body, str):
        params.update(parse(body))
    return params


def legacy_request_data(url, method, post_data=None):
    packet = {'type': 'Adobe Analytics (Legacy)', 'url': url, 'method': method,
              'post_data': post_data if method == 'POST' else None}
    packet['params'] = collect_legacy_params(packet)
    return packet


def get_nested_value(data, path, separator="."):
    if not data or not isinstance(data, dict):
        return None
    current = data
    path_parts = path.split(separator)
    for position, key in enumerate(path_parts):
        remaining = separator.join(path_parts[position:])
        if isinstance(current, dict) and remaining in current:
            return current[remaining]
        if isinstance(current, dict) and key in current:
            current = current[key]
            continue
        indexed_key = re.fullmatch(r"([^\[\]]+)\[(\d+)\]", key)
        if not indexed_key or not isinstance(current, dict):
            return None
        items = current.get(indexed_key.group(1))
        index = int(indexed_key.group(2))
        if not isinstance(items, list) or index >= len(items):
            return None
        current = items[index]
    return current


def normalize_url(value):
    if not value or not isinstance(value, str):
        return ""
    try:
        parsed = urllib.parse.urlparse(value)
        if not parsed.netloc:
            return value.split("?", 1)[0].rstrip("/")
        path = parsed.path.rstrip("/") or "/"
        return f"{parsed.netloc.lower()}{path}"
    except Exception:
        return value.split("?", 1)[0].rstrip("/")


def normalize_events(value):
    if not value:
        return ""
    values = value if isinstance(value, list) else str(value).split(",")
    names = sorted({str(item).split("=", 1)[0].strip() for item in values if str(item).strip()})
    return ",".join(names)


def first_xdm_event(packet):
    payload = packet.get("xdm_payload", {}) if packet else {}
    if not isinstance(payload, dict):
        return {}
    events = payload.get("events", [])
    return events[0] if events and isinstance(events[0], dict) else {}


def analytics_events_for_display(event):
    """Render XDM custom events as an Analytics events string without changing raw data."""
    data = get_nested_value(event, "data.__adobe.analytics")
    if isinstance(data, dict) and "events" in data:
        # Adobe's data.events overrides XDM events, including an explicit empty string.
        return data["events"]
    analytics = get_nested_value(event, "xdm._experience.analytics")
    if not isinstance(analytics, dict):
        return None
    found = []
    for group, events in analytics.items():
        if not re.fullmatch(r"event\d+to\d+", group) or not isinstance(events, dict):
            continue
        for name, measure in events.items():
            match = re.fullmatch(r"event(\d+)", name)
            if not match or not isinstance(measure, dict):
                continue
            value = measure.get("value")
            serial_id = measure.get("id")
            if value is None and serial_id is None:
                continue
            token = name
            if value is not None and value != 1:
                token += f"={value}"
            if serial_id is not None and str(serial_id) != "":
                token += f":{serial_id}"
            found.append((int(match.group(1)), token))
    return ",".join(token for _, token in sorted(found)) if found else None


class AdobeAnalyticsAdapter(MeasurementAdapter):
    key = "AA"
    sheet_name = "Adobe Analytics"
    display_name = "Adobe Analytics"
    aliases = ("adobe", "adobe analytics", "aep", "aep web sdk")

    def discover_mappings(self, packets, existing):
        known_keys = {row['source_key'] for row in existing}
        covered = set()
        for row in existing:
            if row['primary_path']:
                path = row['primary_path']
                covered.add(path if path.startswith('xdm.') else 'xdm.' + path)
            if row['secondary_path']:
                covered.add(row['secondary_path'])
                if row['source_key']:
                    covered.add('data.__adobe.analytics.' + row['source_key'])
        found = {}
        if "events" not in known_keys and any(
            analytics_events_for_display(first_xdm_event(packet)) is not None for packet in packets
        ):
            found['events'] = dict(source_key='events', primary_path='',
                                  secondary_path='data.__adobe.analytics.events', label='Events',
                                  description='Web SDKのXDMカスタムイベントをevents形式で表示（Data指定優先）')

        def walk(value, parts):
            path = '.'.join(parts)
            if any(path == p or path.startswith(p + '.') or path.startswith(p + '[')
                   for p in covered):
                return
            # 配列は商品等の構造を保持して1行にする。既存の配列要素指定は個別に除外。
            if isinstance(value, dict) and value:
                for key, child in value.items():
                    walk(child, parts + [key])
            elif isinstance(value, list) and any(p.startswith(path + '[') for p in covered):
                for index, child in enumerate(value):
                    walk(child, parts[:-1] + [parts[-1] + f'[{index}]'])
            else:
                found[path] = dict(source_key='', primary_path=path if parts[0] == 'xdm' else '',
                                   secondary_path=path if parts[0] == 'data' else '', label=path,
                                   description='テンプレート未定義の送信項目（自動追加）')

        for packet in packets:
            for key in collect_legacy_params(packet):
                if key not in known_keys:
                    found['params:' + key] = dict(source_key=key, primary_path='', secondary_path='',
                                                 label=key, description='テンプレート未定義の送信項目（自動追加）')
            event = first_xdm_event(packet)
            for root in ('xdm', 'data'):
                if root in event:
                    walk(event[root], [root])
        return [found[key] for key in sorted(found)]

    def matches_event(self, event):
        event_type = event.get("type", "")
        url_or_raw = event.get("url") or event.get("raw", "")
        return (
            event_type in ("Adobe Analytics (Legacy)", "AEP Web SDK")
            or "/b/ss/" in url_or_raw
            or "edge.adobedc.net" in url_or_raw
        )

    def extract_value(self, packet, mapping):
        if not packet or not isinstance(packet, dict):
            return None

        source_key = mapping.get("source_key", mapping.get("aa_key", ""))
        primary_path = mapping.get("primary_path", mapping.get("xdm_path", ""))
        secondary_path = mapping.get("secondary_path", mapping.get("data_path", ""))
        label = mapping.get("label", mapping.get("tool_name", ""))

        payload = packet.get("xdm_payload")
        events = payload.get("events", []) if isinstance(payload, dict) else []
        if events:
            first_event = events[0]
            analytics_data = first_event.get("data", {}).get("__adobe", {}).get("analytics", {})

            if source_key == "events" or (not source_key and label.lower() == "events"):
                return analytics_events_for_display(first_event)

            if secondary_path:
                value = get_nested_value(first_event, secondary_path)
                if value is not None:
                    return value
                # Dataの短縮キーもXDMより優先する。空文字の明示指定を保持。
                if source_key and source_key in analytics_data:
                    return analytics_data[source_key]

            if primary_path:
                path = primary_path
                full_path = path if path.startswith("xdm.") else f"xdm.{path}"
                value = get_nested_value(first_event, full_path)
                if value is not None:
                    return value

            if label and label in analytics_data:
                return analytics_data[label]
            if source_key and source_key in analytics_data:
                return analytics_data[source_key]

            xdm_data = first_event.get("xdm", {})
            check_key = source_key or label
            if check_key == "g" or check_key.lower() == "page url":
                return xdm_data.get("web", {}).get("webPageDetails", {}).get("URL")
            if check_key == "r" or check_key.lower() == "referrer":
                return xdm_data.get("web", {}).get("webReferrer", {}).get("URL")
            if check_key == "pageName" or check_key.lower() == "page name":
                return xdm_data.get("web", {}).get("webPageDetails", {}).get("name")
            if check_key == "events":
                return analytics_data.get("events")

        params = collect_legacy_params(packet)
        if source_key and source_key in params:
            return params[source_key]
        return None

    def packet_identity(self, packet):
        if not packet:
            return {}

        if packet.get("type", "") == "AEP Web SDK":
            event = first_xdm_event(packet)
            xdm = event.get("xdm", {}) if isinstance(event, dict) else {}
            analytics = event.get("data", {}).get("__adobe", {}).get("analytics", {}) if isinstance(event, dict) else {}
            page_details = xdm.get("web", {}).get("webPageDetails", {}) if isinstance(xdm, dict) else {}
            event_name = xdm.get("eventType") or analytics.get("pev2") or ""
            return {
                "tool": self.key,
                "source": "AEP Web SDK",
                "event": str(event_name).strip(),
                "page": str(page_details.get("name") or analytics.get("pageName") or "").strip(),
                "url": normalize_url(page_details.get("URL") or analytics.get("g") or ""),
                "account": str(analytics.get("rsid") or "").strip(),
                "events": normalize_events(analytics.get("events")),
            }

        params = collect_legacy_params(packet)
        pe = str(params.get("pe", "")).strip()
        pev2 = str(params.get("pev2", "")).strip()
        return {
            "tool": self.key,
            "source": self.display_name,
            "event": f"{pe}:{pev2}" if pe or pev2 else "",
            "page": str(params.get("pageName", "")).strip(),
            "url": normalize_url(params.get("g", "")),
            "account": str(params.get("rsid") or params.get("s_account") or "").strip(),
            "events": normalize_events(params.get("events")),
        }
