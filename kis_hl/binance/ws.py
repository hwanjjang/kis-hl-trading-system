from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Iterable

from kis_hl.binance.client import KLINE_INTERVALS, BinanceFuturesClient
from kis_hl.config import BinanceConfig
from kis_hl.streaming import (
    Clock,
    MaintainedWebSocketClient,
    PriceTick,
    Sleeper,
    TransportFactory,
    WebSocketClientTransport,
    WebSocketConnection,
    WebSocketStatus,
)

logger = logging.getLogger(__name__)

PayloadHandler = Callable[[dict[str, Any]], None]

BINANCE_SOURCE = "binance"
BINANCE_MARKET = "usdm_futures"
LISTEN_KEY_EXPIRED_EVENT = "listenKeyExpired"
ORDER_UPDATE_EVENT = "ORDER_TRADE_UPDATE"


# ---- stream names and URLs ---------------------------------------------------------


def mark_price_stream(symbol: str, *, fast: bool = False) -> str:
    return f"{_stream_symbol(symbol)}@markPrice" + ("@1s" if fast else "")


def book_ticker_stream(symbol: str) -> str:
    return f"{_stream_symbol(symbol)}@bookTicker"


def kline_stream(symbol: str, interval: str) -> str:
    if interval not in KLINE_INTERVALS:
        raise ValueError(
            f"Unsupported Binance kline interval {interval!r}; valid: {', '.join(KLINE_INTERVALS)}"
        )
    return f"{_stream_symbol(symbol)}@kline_{interval}"


def agg_trade_stream(symbol: str) -> str:
    return f"{_stream_symbol(symbol)}@aggTrade"


# Binance routes futures market streams by tier: high-frequency streams (bookTicker, depth)
# are served only from the ``/public`` root; markPrice, aggTrade, kline, and the rest only from
# ``/market``. One connection can carry streams from one tier only.
PUBLIC_TIER_SUFFIXES = ("@bookTicker", "@depth")


def stream_route(stream: str) -> str:
    """Return ``"public"`` for high-frequency streams and ``"market"`` for everything else."""
    lowered = stream.lower()
    for suffix in PUBLIC_TIER_SUFFIXES:
        if suffix.lower() in lowered:
            return "public"
    return "market"


def market_stream_url(config: BinanceConfig, streams: Iterable[str]) -> str:
    names = [name for name in streams if name]
    if not names:
        raise ValueError("at least one Binance market stream is required")
    routes = {stream_route(name) for name in names}
    if len(routes) > 1:
        raise ValueError(
            "Binance serves bookTicker/depth from the /public route and other market streams from "
            "/market; one connection cannot mix them. Run separate streams, e.g. --streams book "
            "and --streams mark,trade"
        )
    base = config.ws_public_url if routes == {"public"} else config.ws_market_url
    return f"{base}/stream?streams=" + "/".join(names)


def user_stream_url(config: BinanceConfig, listen_key: str) -> str:
    if not listen_key:
        raise ValueError("listen_key is required")
    return f"{config.ws_user_url}/ws/{listen_key}"


# ---- market stream ------------------------------------------------------------------


class BinanceMarketStreamClient:
    """Combined-stream market data over the maintained websocket runner.

    Streams are encoded in the URL, so a reconnect re-subscribes with no client state.
    Binance sends protocol ping frames; ``websocket-client`` answers them automatically.
    """

    def __init__(
        self,
        config: BinanceConfig,
        *,
        streams: Iterable[str],
        on_message: PayloadHandler,
        transport_factory: TransportFactory | None = None,
        stale_after_ms: int = 15_000,
    ) -> None:
        self.config = config
        self.streams = tuple(streams)
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
            url=market_stream_url(self.config, self.streams),
            subscriptions=[],
            on_message=self._handle_raw_message,
            transport_factory=self.transport_factory,
            stale_after_ms=self.stale_after_ms,
        )
        return client.run(max_messages=max_messages, max_reconnects=max_reconnects)

    def _handle_raw_message(self, raw: str, _connection: WebSocketConnection) -> None:
        payload = _load_dict(raw)
        if payload is not None:
            self.on_message(payload)


# ---- user data stream ---------------------------------------------------------------


class BinanceUserStreamClient:
    """Order and account events over the user data stream.

    A fresh ``listenKey`` is requested on every (re)connection, the key is kept alive
    every ``keepalive_interval_ms`` (Binance expires keys after 60 minutes), and a
    ``listenKeyExpired`` event forces a reconnect, which obtains a new key.
    """

    def __init__(
        self,
        config: BinanceConfig,
        client: BinanceFuturesClient,
        *,
        on_message: PayloadHandler,
        transport_factory: TransportFactory | None = None,
        keepalive_interval_ms: int = 30 * 60 * 1000,
        stale_after_ms: int = 10 * 60 * 1000,
        recv_timeout_seconds: float = 1,
        reconnect_min_delay_ms: int = 1_000,
        reconnect_max_delay_ms: int = 30_000,
        now_ms: Clock | None = None,
        sleep: Sleeper | None = None,
    ) -> None:
        self.config = config
        self.client = client
        self.on_message = on_message
        self.transport_factory = transport_factory or _default_transport_factory
        self.keepalive_interval_ms = keepalive_interval_ms
        self.stale_after_ms = stale_after_ms
        self.recv_timeout_seconds = recv_timeout_seconds
        self.reconnect_min_delay_ms = reconnect_min_delay_ms
        self.reconnect_max_delay_ms = reconnect_max_delay_ms
        self.now_ms = now_ms or _time_ms
        self.sleep = sleep
        self.listen_key: str | None = None
        self._last_keepalive_ms: int | None = None

    def run(
        self,
        *,
        max_messages: int | None = None,
        max_reconnects: int | None = None,
    ) -> WebSocketStatus:
        runner = MaintainedWebSocketClient(
            url=self.config.ws_user_url,
            subscriptions=[],
            on_message=self._handle_raw_message,
            transport_factory=self._connect_with_fresh_listen_key,
            stale_after_ms=self.stale_after_ms,
            recv_timeout_seconds=self.recv_timeout_seconds,
            reconnect_min_delay_ms=self.reconnect_min_delay_ms,
            reconnect_max_delay_ms=self.reconnect_max_delay_ms,
            now_ms=self.now_ms,
            sleep=self.sleep,
            on_idle=self._keepalive_if_due,
        )
        return runner.run(max_messages=max_messages, max_reconnects=max_reconnects)

    def _connect_with_fresh_listen_key(self, _url: str, timeout_seconds: float):
        self.listen_key = self.client.create_listen_key()
        self._last_keepalive_ms = self.now_ms()
        return self.transport_factory(user_stream_url(self.config, self.listen_key), timeout_seconds)

    def _keepalive_if_due(self) -> None:
        now = self.now_ms()
        last = self._last_keepalive_ms if self._last_keepalive_ms is not None else now
        if now - last >= self.keepalive_interval_ms:
            self.client.keepalive_listen_key()
            self._last_keepalive_ms = now

    def _handle_raw_message(self, raw: str, _connection: WebSocketConnection) -> None:
        payload = _load_dict(raw)
        if payload is None:
            return
        if payload.get("e") == LISTEN_KEY_EXPIRED_EVENT:
            logger.warning("binance_listen_key_expired")
            raise RuntimeError("listenKeyExpired: reconnecting with a new listenKey")
        self._keepalive_if_due()
        self.on_message(payload)


# ---- parsers ------------------------------------------------------------------------


def parse_market_ticks(payload: Any, *, received_at_ms: int) -> list[PriceTick]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    event = data.get("e")
    symbol = data.get("s")
    if not isinstance(symbol, str) or not symbol:
        return []
    try:
        if event == "markPriceUpdate":
            price = Decimal(str(data["p"]))
            raw = {
                "kind": "mark_price",
                "mark_price": data.get("p"),
                "index_price": data.get("i"),
                "funding_rate": data.get("r"),
                "next_funding_time_ms": data.get("T"),
                "price": data.get("p"),
            }
            size = None
        elif event == "bookTicker":
            bid = Decimal(str(data["b"]))
            ask = Decimal(str(data["a"]))
            price = (bid + ask) / 2
            raw = {
                "kind": "book_ticker",
                "bid": data.get("b"),
                "bid_qty": data.get("B"),
                "ask": data.get("a"),
                "ask_qty": data.get("A"),
                "update_id": data.get("u"),
                "price": str(price),
            }
            size = None
        elif event == "kline":
            candle = data.get("k")
            if not isinstance(candle, dict):
                return []
            price = Decimal(str(candle["c"]))
            size = Decimal(str(candle["v"]))
            raw = {
                "kind": "kline",
                "interval": candle.get("i"),
                "start_time_ms": candle.get("t"),
                "end_time_ms": candle.get("T"),
                "open": candle.get("o"),
                "high": candle.get("h"),
                "low": candle.get("l"),
                "close": candle.get("c"),
                "volume": candle.get("v"),
                "closed": bool(candle.get("x")),
                "price": candle.get("c"),
            }
        elif event == "aggTrade":
            price = Decimal(str(data["p"]))
            size = Decimal(str(data["q"]))
            raw = {
                "kind": "agg_trade",
                "trade_id": data.get("a"),
                "trade_time_ms": data.get("T"),
                "buyer_is_maker": data.get("m"),
                "quantity": data.get("q"),
                "price": data.get("p"),
            }
        else:
            return []
    except (KeyError, InvalidOperation, ValueError, TypeError):
        return []
    raw["event"] = event
    raw["event_time_ms"] = data.get("E")
    return [
        PriceTick(
            source=BINANCE_SOURCE,
            symbol=symbol,
            price=price,
            received_at_ms=received_at_ms,
            event_time=_optional_int(data.get("E")),
            size=size,
            raw=raw,
        )
    ]


@dataclass(frozen=True, slots=True)
class OrderEvent:
    venue: str
    symbol: str
    order_id: str | None
    client_order_id: str | None
    side: str | None
    order_type: str | None
    execution_type: str | None
    status: str | None
    price: Decimal | None
    avg_price: Decimal | None
    orig_qty: Decimal | None
    last_filled_qty: Decimal | None
    cum_filled_qty: Decimal | None
    stop_price: Decimal | None
    reduce_only: bool
    event_time_ms: int | None
    received_at_ms: int
    raw: dict[str, Any] = field(default_factory=dict)


def parse_order_event(payload: Any, *, received_at_ms: int) -> OrderEvent | None:
    if not isinstance(payload, dict) or payload.get("e") != ORDER_UPDATE_EVENT:
        return None
    order = payload.get("o")
    if not isinstance(order, dict):
        return None
    symbol = order.get("s")
    if not isinstance(symbol, str) or not symbol:
        return None
    return OrderEvent(
        venue=BINANCE_SOURCE,
        symbol=symbol,
        order_id=_optional_str(order.get("i")),
        client_order_id=_optional_str(order.get("c")),
        side=_optional_str(order.get("S")),
        order_type=_optional_str(order.get("o")),
        execution_type=_optional_str(order.get("x")),
        status=_optional_str(order.get("X")),
        price=_optional_decimal(order.get("p")),
        avg_price=_optional_decimal(order.get("ap")),
        orig_qty=_optional_decimal(order.get("q")),
        last_filled_qty=_optional_decimal(order.get("l")),
        cum_filled_qty=_optional_decimal(order.get("z")),
        stop_price=_optional_decimal(order.get("sp")),
        reduce_only=bool(order.get("R", False)),
        event_time_ms=_optional_int(payload.get("E")),
        received_at_ms=received_at_ms,
        raw=payload,
    )


def order_event_to_row(event: OrderEvent) -> dict[str, Any]:
    """Keyword arguments for ``kis_hl.storage.store_order_event``."""
    return {
        "venue": event.venue,
        "symbol": event.symbol,
        "order_id": event.order_id,
        "client_order_id": event.client_order_id,
        "side": event.side,
        "order_type": event.order_type,
        "execution_type": event.execution_type,
        "status": event.status,
        "price": _optional_text(event.price),
        "avg_price": _optional_text(event.avg_price),
        "orig_qty": _optional_text(event.orig_qty),
        "last_filled_qty": _optional_text(event.last_filled_qty),
        "cum_filled_qty": _optional_text(event.cum_filled_qty),
        "stop_price": _optional_text(event.stop_price),
        "reduce_only": event.reduce_only,
        "event_time_ms": event.event_time_ms,
        "received_at_ms": event.received_at_ms,
        "payload": event.raw,
    }


# ---- helpers -----------------------------------------------------------------------


def _stream_symbol(symbol: str) -> str:
    if not symbol or not symbol.strip():
        raise ValueError("symbol is required")
    return symbol.strip().lower()


def _load_dict(raw: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.debug("binance_ws_non_json_frame")
        return None
    return payload if isinstance(payload, dict) else None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _optional_text(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _default_transport_factory(url: str, timeout_seconds: float):
    return WebSocketClientTransport(url, timeout_seconds=timeout_seconds)


def _time_ms() -> int:
    return int(time.time() * 1000)
