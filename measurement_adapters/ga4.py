import urllib.parse

from .base import MeasurementAdapter


def parse_query_string(raw_value):
    if not raw_value or not isinstance(raw_value, str):
        return {}
    query = raw_value.split("?", 1)[-1]
    params = {}
    for pair in query.split("&"):
        if "=" in pair:
            key, value = pair.split("=", 1)
            params[key] = urllib.parse.unquote(value)
    return params


def collect_params(packet):
    params = {}
    if not packet:
        return params

    params.update(parse_query_string(packet.get("url", "")))
    params.update(parse_query_string(packet.get("raw", "")))
    for key, value in packet.get("params", {}).items():
        params[key] = value[0] if isinstance(value, list) and value else value
    post_data = packet.get("post_data")
    if isinstance(post_data, str):
        params.update(parse_query_string(post_data))
    return params


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


class GA4Adapter(MeasurementAdapter):
    key = "GA4"
    sheet_name = "GA4"
    display_name = "GA4"
    aliases = ("google analytics 4",)

    def matches_event(self, event):
        event_type = event.get("type", "")
        url_or_raw = event.get("url") or event.get("raw", "")
        return (
            event_type == "GA4"
            or "tid=G-" in url_or_raw
            or "google-analytics.com" in url_or_raw
        )

    def extract_value(self, packet, mapping):
        if not packet:
            return None
        source_key = mapping.get("source_key", mapping.get("aa_key", ""))
        return collect_params(packet).get(source_key)

    def packet_identity(self, packet):
        if not packet:
            return {}
        params = collect_params(packet)
        return {
            "tool": self.key,
            "source": self.display_name,
            "event": str(params.get("en", "")).strip(),
            "page": str(params.get("dt", "")).strip(),
            "url": normalize_url(params.get("dl", "")),
            "account": str(params.get("tid", "")).strip(),
            "events": "",
        }
