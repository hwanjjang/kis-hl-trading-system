from __future__ import annotations

import json
import socket
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Iterable, Protocol

from kis_hl.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PriceTick:
    source: str
    symbol: str
    price: Decimal
    received_at_ms: int
    exchange_code: str | None = None
    event_time: str | None = None
    size: Decimal | None = None
    raw: Any = None


@dataclass(frozen=True, slots=True)
class WebSocketSubscription:
    name: str
    payload: str | dict[str, Any]


@dataclass(slots=True)
class WebSocketStatus:
    url: str
    state: str = "idle"
    connection_count: int = 0
    reconnect_count: int = 0
    last_connected_at_ms: int | None = None
    last_message_at_ms: int | None = None
    last_sent_at_ms: int | None = None
    last_error: str | None = None
    last_disconnect_reason: str | None = None

    def is_stale(self, *, now_ms: int, stale_after_ms: int) -> bool:
        if self.last_message_at_ms is None:
            return False
        return now_ms - self.last_message_at_ms >= stale_after_ms


class WebSocketTransport(Protocol):
    def send_text(self, text: str) -> None:
        ...

    def recv_text(self, *, timeout_seconds: float | None = None) -> str:
        ...

    def close(self) -> None:
        ...


class WebSocketClientTransport:
    def __init__(self, url: str, *, timeout_seconds: float = 10) -> None:
        try:
            import websocket
        except ImportError as exc:
            raise RuntimeError(
                "Install websocket-client before using live websocket streams"
            ) from exc
        self._websocket_module = websocket
        self._socket = websocket.create_connection(url, timeout=timeout_seconds)

    def send_text(self, text: str) -> None:
        self._socket.send(text)

    def recv_text(self, *, timeout_seconds: float | None = None) -> str:
        if timeout_seconds is not None:
            self._socket.settimeout(timeout_seconds)
        try:
            data = self._socket.recv()
        except (socket.timeout, TimeoutError, self._websocket_module.WebSocketTimeoutException) as exc:
            raise TimeoutError("websocket receive timed out") from exc
        if isinstance(data, bytes):
            return data.decode("utf-8")
        return str(data)

    def close(self) -> None:
        self._socket.close()


class WebSocketConnection:
    def __init__(
        self,
        transport: WebSocketTransport,
        status: WebSocketStatus,
        now_ms: Clock | None = None,
    ) -> None:
        self._transport = transport
        self.status = status
        self._now_ms = now_ms or _time_ms

    def send_text(self, text: str) -> None:
        self._transport.send_text(text)
        self.status.last_sent_at_ms = self._now_ms()

    def send_json(self, payload: dict[str, Any]) -> None:
        self.send_text(json.dumps(payload, sort_keys=True))


MessageHandler = Callable[[str, WebSocketConnection], None]
TransportFactory = Callable[[str, float], WebSocketTransport]
Clock = Callable[[], int]
Sleeper = Callable[[float], None]


class MaintainedWebSocketClient:
    def __init__(
        self,
        *,
        url: str,
        subscriptions: Iterable[WebSocketSubscription],
        on_message: MessageHandler,
        transport_factory: TransportFactory | None = None,
        stale_after_ms: int = 15_000,
        reconnect_min_delay_ms: int = 1_000,
        reconnect_max_delay_ms: int = 30_000,
        connect_timeout_seconds: float = 10,
        recv_timeout_seconds: float = 1,
        heartbeat_payload: dict[str, Any] | None = None,
        heartbeat_interval_ms: int = 50_000,
        now_ms: Clock | None = None,
        sleep: Sleeper | None = None,
    ) -> None:
        self.url = url
        self.subscriptions = tuple(subscriptions)
        self.on_message = on_message
        self.transport_factory = transport_factory or _default_transport_factory
        self.stale_after_ms = stale_after_ms
        self.reconnect_min_delay_ms = reconnect_min_delay_ms
        self.reconnect_max_delay_ms = reconnect_max_delay_ms
        self.connect_timeout_seconds = connect_timeout_seconds
        self.recv_timeout_seconds = recv_timeout_seconds
        self.heartbeat_payload = heartbeat_payload
        self.heartbeat_interval_ms = heartbeat_interval_ms
        self.now_ms = now_ms or _time_ms
        self.sleep = sleep or time.sleep
        self.status = WebSocketStatus(url=url)
        self._stopped = False

    def stop(self) -> None:
        self._stopped = True

    def run(
        self,
        *,
        max_messages: int | None = None,
        max_reconnects: int | None = None,
    ) -> WebSocketStatus:
        handled_messages = 0
        reconnects = 0
        while not self._stopped:
            transport: WebSocketTransport | None = None
            try:
                self.status.state = "connecting"
                transport = self.transport_factory(self.url, self.connect_timeout_seconds)
                connection = WebSocketConnection(transport, self.status, self.now_ms)
                connected_at = self.now_ms()
                self.status.state = "connected"
                self.status.connection_count += 1
                self.status.last_connected_at_ms = connected_at
                self.status.last_message_at_ms = connected_at
                self.status.last_disconnect_reason = None
                self._send_subscriptions(connection)
                while not self._stopped:
                    try:
                        raw = transport.recv_text(timeout_seconds=self.recv_timeout_seconds)
                    except TimeoutError:
                        self._send_heartbeat_if_due(connection)
                        if self.status.is_stale(
                            now_ms=self.now_ms(),
                            stale_after_ms=self.stale_after_ms,
                        ):
                            raise RuntimeError("websocket stream is stale")
                        continue
                    self.status.last_message_at_ms = self.now_ms()
                    self.on_message(raw, connection)
                    handled_messages += 1
                    if max_messages is not None and handled_messages >= max_messages:
                        self.status.state = "stopped"
                        return self.status
            except Exception as exc:
                self.status.last_error = str(exc)
                self.status.last_disconnect_reason = str(exc)
                logger.warning(
                    "websocket_connection_interrupted",
                    extra={"url": self.url, "error": str(exc), "reconnects": reconnects},
                )
            finally:
                if transport is not None:
                    try:
                        transport.close()
                    except Exception as exc:
                        logger.debug("websocket_close_failed", extra={"url": self.url, "error": str(exc)})
                if self.status.state != "stopped":
                    self.status.state = "disconnected"
            if self._stopped:
                break
            if max_reconnects is not None and reconnects >= max_reconnects:
                break
            reconnects += 1
            self.status.reconnect_count = reconnects
            self.sleep(self._reconnect_delay_seconds(reconnects))
        return self.status

    def _send_subscriptions(self, connection: WebSocketConnection) -> None:
        for subscription in self.subscriptions:
            if isinstance(subscription.payload, str):
                connection.send_text(subscription.payload)
            else:
                connection.send_json(subscription.payload)

    def _send_heartbeat_if_due(self, connection: WebSocketConnection) -> None:
        if not self.heartbeat_payload:
            return
        now = self.now_ms()
        last_sent = self.status.last_sent_at_ms or 0
        if now - last_sent >= self.heartbeat_interval_ms:
            connection.send_json(self.heartbeat_payload)

    def _reconnect_delay_seconds(self, reconnects: int) -> float:
        delay_ms = self.reconnect_min_delay_ms * (2 ** max(0, reconnects - 1))
        return min(delay_ms, self.reconnect_max_delay_ms) / 1000


def _default_transport_factory(url: str, timeout_seconds: float) -> WebSocketTransport:
    return WebSocketClientTransport(url, timeout_seconds=timeout_seconds)


def _time_ms() -> int:
    return int(time.time() * 1000)
