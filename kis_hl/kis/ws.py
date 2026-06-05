from __future__ import annotations

import json
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Iterable

from kis_hl.config import KisConfig
from kis_hl.kis.client import KisClient
from kis_hl.streaming import (
    MaintainedWebSocketClient,
    PriceTick,
    TransportFactory,
    WebSocketConnection,
    WebSocketStatus,
    WebSocketSubscription,
)

KIS_DOMESTIC_TRADE_TR_ID = "H0STCNT0"
KIS_OVERSEAS_TRADE_TR_ID = "HDFSCNT0"

_DOMESTIC_PRICE_FIELDS = (
    "MKSC_SHRN_ISCD",
    "STCK_CNTG_HOUR",
    "STCK_PRPR",
    "PRDY_VRSS_SIGN",
    "PRDY_VRSS",
    "PRDY_CTRT",
    "WGHN_AVRG_STCK_PRC",
    "STCK_OPRC",
    "STCK_HGPR",
    "STCK_LWPR",
    "ASKP1",
    "BIDP1",
    "CNTG_VOL",
    "ACML_VOL",
    "ACML_TR_PBMN",
    "SELN_CNTG_CSNU",
    "SHNU_CNTG_CSNU",
    "NTBY_CNTG_CSNU",
    "CTTR",
    "SELN_CNTG_SMTN",
    "SHNU_CNTG_SMTN",
    "CCLD_DVSN",
    "SHNU_RATE",
    "PRDY_VOL_VRSS_ACML_VOL_RATE",
    "OPRC_HOUR",
    "OPRC_VRSS_PRPR_SIGN",
    "OPRC_VRSS_PRPR",
    "HGPR_HOUR",
    "HGPR_VRSS_PRPR_SIGN",
    "HGPR_VRSS_PRPR",
    "LWPR_HOUR",
    "LWPR_VRSS_PRPR_SIGN",
    "LWPR_VRSS_PRPR",
    "BSOP_DATE",
    "NEW_MKOP_CLS_CODE",
    "TRHT_YN",
    "ASKP_RSQN1",
    "BIDP_RSQN1",
    "TOTAL_ASKP_RSQN",
    "TOTAL_BIDP_RSQN",
    "VOL_TNRT",
    "PRDY_SMNS_HOUR_ACML_VOL",
    "PRDY_SMNS_HOUR_ACML_VOL_RATE",
    "HOUR_CLS_CODE",
    "MRKT_TRTM_CLS_CODE",
    "VI_STND_PRC",
)

_OVERSEAS_PRICE_FIELDS = (
    "SYMB",
    "ZDIV",
    "TYMD",
    "XYMD",
    "XHMS",
    "KYMD",
    "KHMS",
    "OPEN",
    "HIGH",
    "LOW",
    "LAST",
    "SIGN",
    "DIFF",
    "RATE",
    "PBID",
    "PASK",
    "VBID",
    "VASK",
    "EVOL",
    "TVOL",
    "TAMT",
    "BIVL",
    "ASVL",
    "STRN",
    "MTYP",
)


TickHandler = Callable[[PriceTick], None]
MessageHandler = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class KisWebSocketSubscription:
    tr_id: str
    tr_key: str
    name: str | None = None

    def to_websocket_subscription(self, approval_key: str) -> WebSocketSubscription:
        return WebSocketSubscription(
            name=self.name or f"{self.tr_id}:{self.tr_key}",
            payload=build_kis_subscribe_message(
                approval_key=approval_key,
                tr_id=self.tr_id,
                tr_key=self.tr_key,
            ),
        )


class KisWebSocketClient:
    def __init__(
        self,
        config: KisConfig,
        *,
        subscriptions: Iterable[KisWebSocketSubscription],
        on_tick: TickHandler,
        on_message: MessageHandler | None = None,
        kis_client: KisClient | None = None,
        approval_key: str | None = None,
        transport_factory: TransportFactory | None = None,
        stale_after_ms: int = 15_000,
    ) -> None:
        self.config = config
        self.subscriptions = tuple(subscriptions)
        self.on_tick = on_tick
        self.on_message = on_message
        self.kis_client = kis_client or KisClient(config)
        self.approval_key = approval_key
        self.transport_factory = transport_factory
        self.stale_after_ms = stale_after_ms

    def run(
        self,
        *,
        max_messages: int | None = None,
        max_reconnects: int | None = None,
    ) -> WebSocketStatus:
        if not self.config.ws_url:
            raise RuntimeError("KIS websocket URL is missing")
        approval_key = self.approval_key or self.kis_client.get_websocket_approval_key()
        subscriptions = [
            subscription.to_websocket_subscription(approval_key)
            for subscription in self.subscriptions
        ]
        client = MaintainedWebSocketClient(
            url=_join_kis_ws_url(self.config.ws_url),
            subscriptions=subscriptions,
            on_message=self._handle_raw_message,
            transport_factory=self.transport_factory,
            stale_after_ms=self.stale_after_ms,
        )
        return client.run(max_messages=max_messages, max_reconnects=max_reconnects)

    def _handle_raw_message(self, raw: str, connection: WebSocketConnection) -> None:
        if is_kis_ping_message(raw):
            connection.send_text(raw)
            return
        if self.on_message:
            self.on_message(raw)
        received_at_ms = int(time.time() * 1000)
        for tick in parse_kis_price_ticks(raw, received_at_ms=received_at_ms):
            self.on_tick(tick)


def build_kis_subscribe_message(
    *,
    approval_key: str,
    tr_id: str,
    tr_key: str,
    tr_type: str = "1",
    custtype: str = "P",
) -> dict[str, Any]:
    return {
        "header": {
            "approval_key": approval_key,
            "tr_type": tr_type,
            "custtype": custtype,
        },
        "body": {
            "input": {
                "tr_id": tr_id,
                "tr_key": tr_key,
            }
        },
    }


def is_kis_ping_message(raw: str) -> bool:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return False
    if not isinstance(payload, dict):
        return False
    header = payload.get("header")
    return isinstance(header, dict) and header.get("tr_id") == "PINGPONG"


def parse_kis_price_ticks(raw: str, *, received_at_ms: int) -> list[PriceTick]:
    if not raw.startswith(("0|", "1|")):
        return []
    parts = raw.split("|", 3)
    if len(parts) != 4:
        return []
    _encrypted, tr_id, raw_count, data = parts
    try:
        count = int(raw_count)
    except ValueError:
        count = 0
    if tr_id == KIS_DOMESTIC_TRADE_TR_ID:
        return _parse_records(
            data=data,
            count=count,
            fields=_DOMESTIC_PRICE_FIELDS,
            source="kis",
            exchange_code="KRX",
            symbol_field="MKSC_SHRN_ISCD",
            price_field="STCK_PRPR",
            event_time_fields=("BSOP_DATE", "STCK_CNTG_HOUR"),
            received_at_ms=received_at_ms,
            raw=raw,
        )
    if tr_id == KIS_OVERSEAS_TRADE_TR_ID:
        return _parse_records(
            data=data,
            count=count,
            fields=_OVERSEAS_PRICE_FIELDS,
            source="kis",
            exchange_code=None,
            symbol_field="SYMB",
            price_field="LAST",
            event_time_fields=("XYMD", "XHMS"),
            received_at_ms=received_at_ms,
            raw=raw,
        )
    return []


def _parse_records(
    *,
    data: str,
    count: int,
    fields: tuple[str, ...],
    source: str,
    exchange_code: str | None,
    symbol_field: str,
    price_field: str,
    event_time_fields: tuple[str, str],
    received_at_ms: int,
    raw: str,
) -> list[PriceTick]:
    values = data.split("^")
    size = len(fields)
    records = []
    chunks = [values[index : index + size] for index in range(0, len(values), size)]
    for chunk in chunks[: count or len(chunks)]:
        if len(chunk) < size:
            continue
        record = {fields[index]: chunk[index] for index in range(size)}
        symbol = record.get(symbol_field, "").strip()
        raw_price = record.get(price_field, "").strip()
        if not symbol or not raw_price:
            continue
        try:
            price = Decimal(raw_price)
        except (InvalidOperation, ValueError):
            continue
        event_date = record.get(event_time_fields[0], "").strip()
        event_time = record.get(event_time_fields[1], "").strip()
        records.append(
            PriceTick(
                source=source,
                symbol=symbol,
                price=price,
                received_at_ms=received_at_ms,
                exchange_code=exchange_code,
                event_time=(event_date + event_time) or None,
                raw={"record": record, "message": raw},
            )
        )
    return records


def _join_kis_ws_url(base_url: str) -> str:
    cleaned = base_url.rstrip("/")
    if cleaned.endswith("/tryitout"):
        return cleaned
    return cleaned + "/tryitout"
