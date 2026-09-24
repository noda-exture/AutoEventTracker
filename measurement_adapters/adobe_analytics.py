import urllib.parse

from .base import MeasurementAdapter


def get_nested_value(data, path, separator="."):
    if not data or not isinstance(data, dict):
        return None
    current = data
    for key in path.split(separator):
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
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


class AdobeAnalyticsAdapter(MeasurementAdapter):
    key = "AA"
    sheet_name = "Adobe Analytics"
    display_name = "Adobe Analytics"
    aliases = ("adobe", "adobe analytics", "aep", "aep web sdk")

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

        events = packet.get("xdm_payload", {}).get("events", [])
        if events:
            first_event = events[0]
            analytics_data = first_event.get("data", {}).get("__adobe", {}).get("analytics", {})

            if secondary_path:
                value = get_nested_value(first_event, secondary_path)
                if value is not None:
                    return value

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
                return analytics_data.get("events", xdm_data.get("eventType"))

        params = packet.get("params", {})
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

        params = packet.get("params", {})
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
