from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable


class MeasurementAdapter(ABC):
    """計測サービス固有の判定・抽出・照合情報を提供する基底クラス。"""

    key = ""
    sheet_name = ""
    display_name = ""
    aliases = ()

    def filter_events(self, events: Iterable[dict]) -> list[dict]:
        return [event for event in events if self.matches_event(event)]

    @abstractmethod
    def matches_event(self, event: dict) -> bool:
        """イベントがこの計測サービスの通信か判定する。"""

    @abstractmethod
    def extract_value(self, packet: dict | None, mapping: dict):
        """テンプレートの1項目に対応する値をパケットから取り出す。"""

    @abstractmethod
    def packet_identity(self, packet: dict | None) -> dict:
        """同一ステップ内の新旧パケット照合に使う安定した識別情報を返す。"""

    def packet_display_name(self, packet: dict | None) -> str:
        identity = self.packet_identity(packet)
        label = (
            identity.get("event")
            or identity.get("page")
            or identity.get("url")
            or identity.get("source")
            or "packet"
        )
        label = str(label).replace("\n", " ").strip()
        return label[:48] + ("…" if len(label) > 48 else "")
