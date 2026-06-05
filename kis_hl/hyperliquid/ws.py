from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Iterable

from kis_hl.config import HyperliquidConfig
from kis_hl.streaming import (
    MaintainedWebSocketClient,
    PriceTick,
    TransportFactory,
    WebSocketConnection,
    WebSocketStatus,
    WebSocketSubscription,
)


PayloadHandler = Callable[[dict[str, Any]], None]


def default_hyperliquid_ws_url(config: HyperliquidConfig) -> str:
    if config.ws_url:
        return config.ws_url
    base = config.base_url.rstrip("/")
    if base.startswith("https://"):
        base = "wss://" + base[len("https://") :]
    elif base.startswith("http://"):
        base = "ws://" + base[len("http://") :]
    return base + "/ws"


def all_mids_subscription(*, dex: str | None = None) -> WebSocketSubscription:
    subscription: dict[str, Any] = {"type": "allMids"}
    if dex:
        subscription["dex"] = dex
    return WebSocketSubscription(
        name="allMids" + (f":{dex}" if dex else ""),
        payload={"method": "subscribe", "subscription": subscription},
    )


def user_fills_subscription(user: str) -> WebSocketSubscription:
    return _subscription("userFills", {"type": "userFills", "user": user})


def user_events_subscription(user: str) -> WebSocketSubscription:
    return _subscription("userEvents", {"type": "userEvents", "user": user})


def all_dexs_clearinghouse_state_subscription(user: str) -> WebSocketSubscription:
    return _subscription(
        "allDexsClearinghouseState",
        {"type": "allDexsClearinghouseState", "user": user},
    )


def candle_subscription(*, coin: str, interval: str) -> WebSocketSubscription:
    return _subscription("candle", {"type": "candle", "coin": coin, "interval": interval})


class HyperliquidWebSocketClient:
    def __init__(
        self,
        config: HyperliquidConfig,
        *,
        subscriptions: Iterable[WebSocketSubscription],
        on_message: PayloadHandler,
        transport_factory: TransportFactory | None = None,
        stale_after_ms: int = 15_000,
    ) -> None:
        self.config = config
        self.subscriptions = tuple(subscriptions)
        self.on_message = on_message
        self.transport_factory = transport_factory
        self.stale_after_ms = stale_after_ms

    def run(
        self,
        *,
        max_messages: int | None = None,
        max_reconnects: int | None = None,
    ) -> WebSocketStatus:
        client = MaintainedWebSocketClient(
            url=default_hyperliquid_ws_url(self.config),
            subscriptions=self.subscriptions,
            on_message=self._handle_raw_message,
            transport_factory=self.transport_factory,
            stale_after_ms=self.stale_after_ms,
            heartbeat_payload={"method": "ping"},
            heartbeat_interval_ms=50_000,
        )
        return client.run(max_messages=max_messages, max_reconnects=max_reconnects)

    def _handle_raw_message(self, raw: str, _connection: WebSocketConnection) -> None:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            self.on_message(payload)


def parse_all_mids_ticks(raw: str, *, received_at_ms: int) -> list[PriceTick]:
    payload = json.loads(raw)
    return parse_all_mids_ticks_payload(payload, received_at_ms=received_at_ms)


def parse_all_mids_ticks_payload(payload: dict[str, Any], *, received_at_ms: int) -> list[PriceTick]:
    if not isinstance(payload, dict) or payload.get("channel") != "allMids":
        return []
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    mids = data.get("mids")
    if not isinstance(mids, dict):
        return []
    ticks = []
    for symbol, raw_price in mids.items():
        try:
            price = Decimal(str(raw_price))
        except (InvalidOperation, ValueError):
            continue
        ticks.append(
            PriceTick(
                source="hyperliquid",
                symbol=str(symbol),
                price=price,
                received_at_ms=received_at_ms,
                raw=payload,
            )
        )
    return ticks


def _subscription(name: str, subscription: dict[str, Any]) -> WebSocketSubscription:
    return WebSocketSubscription(
        name=name,
        payload={"method": "subscribe", "subscription": subscription},
    )
