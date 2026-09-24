from .adobe_analytics import AdobeAnalyticsAdapter
from .base import MeasurementAdapter
from .ga4 import GA4Adapter


_ADAPTERS = []


def register_adapter(adapter, *, replace=False):
    """計測サービスを登録する。KARTE等は同じインターフェースで追加できる。"""
    if not isinstance(adapter, MeasurementAdapter):
        raise TypeError("adapter must inherit MeasurementAdapter")

    existing = next((item for item in _ADAPTERS if item.key == adapter.key), None)
    if existing:
        if not replace:
            raise ValueError(f"adapter is already registered: {adapter.key}")
        _ADAPTERS.remove(existing)
    _ADAPTERS.append(adapter)
    return adapter


def get_adapter(name):
    if isinstance(name, MeasurementAdapter):
        return name
    normalized = str(name).strip().lower()
    for adapter in _ADAPTERS:
        names = (adapter.key, adapter.sheet_name, adapter.display_name, *adapter.aliases)
        if normalized in {str(candidate).strip().lower() for candidate in names}:
            return adapter
    raise KeyError(f"未登録の計測サービスです: {name}")


def get_registered_adapters():
    return tuple(_ADAPTERS)


register_adapter(GA4Adapter())
register_adapter(AdobeAnalyticsAdapter())


__all__ = [
    "AdobeAnalyticsAdapter",
    "GA4Adapter",
    "MeasurementAdapter",
    "get_adapter",
    "get_registered_adapters",
    "register_adapter",
]
