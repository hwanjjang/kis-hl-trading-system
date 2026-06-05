from __future__ import annotations

import json
import unittest
from decimal import Decimal

from kis_hl.config import HyperliquidConfig, KisConfig
from kis_hl.hyperliquid.ws import (
    HyperliquidWebSocketClient,
    all_mids_subscription,
    default_hyperliquid_ws_url,
    parse_all_mids_ticks,
)
from kis_hl.kis.ws import (
    KisWebSocketSubscription,
    build_kis_subscribe_message,
    is_kis_ping_message,
    parse_kis_price_ticks,
)
from kis_hl.streaming import MaintainedWebSocketClient, WebSocketSubscription


class WebSocketStreamTests(unittest.TestCase):
    def test_maintained_websocket_reconnects_after_stale_timeout(self) -> None:
        now_ms = 0
        handled: list[str] = []
        transports: list[FakeTransport] = []

        def now() -> int:
            return now_ms

        def sleep(seconds: float) -> None:
            nonlocal now_ms
            now_ms += int(seconds * 1000)

        def factory(_url: str, _timeout: float) -> FakeTransport:
            nonlocal now_ms
            if not transports:
                transport = FakeTransport([], now=lambda: now_ms, advance=lambda ms: _advance(ms))
            else:
                transport = FakeTransport(["{\"ok\": true}"], now=lambda: now_ms, advance=lambda ms: _advance(ms))
            transports.append(transport)
            return transport

        def _advance(ms: int) -> None:
            nonlocal now_ms
            now_ms += ms

        client = MaintainedWebSocketClient(
            url="wss://example.test/ws",
            subscriptions=[WebSocketSubscription("test", {"method": "subscribe"})],
            on_message=lambda raw, _connection: handled.append(raw),
            transport_factory=factory,
            stale_after_ms=1000,
            reconnect_min_delay_ms=100,
            reconnect_max_delay_ms=100,
            recv_timeout_seconds=0.1,
            now_ms=now,
            sleep=sleep,
        )

        status = client.run(max_messages=1, max_reconnects=1)

        self.assertEqual(len(transports), 2)
        self.assertEqual(handled, ["{\"ok\": true}"])
        self.assertEqual(status.reconnect_count, 1)
        self.assertTrue(all(transport.closed for transport in transports))
        self.assertEqual(
            transports[0].sent,
            [json.dumps({"method": "subscribe"}, sort_keys=True)],
        )

    def test_hyperliquid_client_sends_subscribe_and_ping_payloads(self) -> None:
        sent: list[str] = []

        class OneMessageTransport:
            closed = False

            def send_text(self, text: str) -> None:
                sent.append(text)

            def recv_text(self, *, timeout_seconds: float | None = None) -> str:
                return json.dumps({"channel": "pong"})

            def close(self) -> None:
                self.closed = True

        config = HyperliquidConfig(
            base_url="https://api.hyperliquid.xyz",
            account_address="0xabc",
            private_key="0x" + "1" * 64,
            key_profile="default",
        )
        client = HyperliquidWebSocketClient(
            config,
            subscriptions=[all_mids_subscription(dex="xyz")],
            on_message=lambda _payload: None,
            transport_factory=lambda _url, _timeout: OneMessageTransport(),
        )
        status = client.run(max_messages=1)

        self.assertEqual(status.connection_count, 1)
        self.assertEqual(
            json.loads(sent[0]),
            {"method": "subscribe", "subscription": {"type": "allMids", "dex": "xyz"}},
        )
        self.assertEqual(default_hyperliquid_ws_url(config), "wss://api.hyperliquid.xyz/ws")

    def test_hyperliquid_all_mids_parser_returns_ticks(self) -> None:
        ticks = parse_all_mids_ticks(
            json.dumps({"channel": "allMids", "data": {"mids": {"xyz:KR200": "350.25"}}}),
            received_at_ms=123,
        )

        self.assertEqual(len(ticks), 1)
        self.assertEqual(ticks[0].source, "hyperliquid")
        self.assertEqual(ticks[0].symbol, "xyz:KR200")
        self.assertEqual(ticks[0].price, Decimal("350.25"))
        self.assertEqual(ticks[0].received_at_ms, 123)

    def test_kis_subscribe_message_matches_official_shape(self) -> None:
        payload = build_kis_subscribe_message(
            approval_key="approval",
            tr_id="H0STCNT0",
            tr_key="005930",
        )

        self.assertEqual(
            payload,
            {
                "header": {
                    "approval_key": "approval",
                    "tr_type": "1",
                    "custtype": "P",
                },
                "body": {"input": {"tr_id": "H0STCNT0", "tr_key": "005930"}},
            },
        )
        self.assertTrue(is_kis_ping_message(json.dumps({"header": {"tr_id": "PINGPONG"}})))

    def test_kis_price_parser_handles_domestic_and_overseas_ticks(self) -> None:
        domestic_values = ["005930", "123456", "75000"] + [""] * 44
        overseas_values = ["AAPL", "", "", "20260527", "123456"] + [""] * 5 + ["180.12"] + [""] * 14

        domestic = parse_kis_price_ticks("0|H0STCNT0|001|" + "^".join(domestic_values), received_at_ms=1)
        overseas = parse_kis_price_ticks("0|HDFSCNT0|001|" + "^".join(overseas_values), received_at_ms=2)

        self.assertEqual(domestic[0].symbol, "005930")
        self.assertEqual(domestic[0].exchange_code, "KRX")
        self.assertEqual(domestic[0].price, Decimal("75000"))
        self.assertEqual(overseas[0].symbol, "AAPL")
        self.assertEqual(overseas[0].price, Decimal("180.12"))

    def test_kis_websocket_subscription_builds_payload_after_approval(self) -> None:
        config = KisConfig(
            mode="live",
            base_url="https://example.test",
            app_key="key",
            app_secret="secret",
            account_id="1234567801",
            account8="12345678",
            product_code2="01",
            hts_id="hts",
            token_dir=__import__("pathlib").Path("/tmp"),
            http_timeout_seconds=1,
            min_request_interval_ms=0,
            rate_limit_retries=0,
            rate_limit_delay_ms=0,
            ws_url="ws://example.test",
        )
        subscription = KisWebSocketSubscription(tr_id="H0STCNT0", tr_key="005930")
        self.assertEqual(subscription.to_websocket_subscription("approval").name, "H0STCNT0:005930")
        self.assertEqual(config.ws_url, "ws://example.test")


class FakeTransport:
    def __init__(
        self,
        messages: list[str],
        *,
        now: callable,
        advance: callable,
    ) -> None:
        self.messages = list(messages)
        self.sent: list[str] = []
        self.closed = False
        self._now = now
        self._advance = advance

    def send_text(self, text: str) -> None:
        self.sent.append(text)

    def recv_text(self, *, timeout_seconds: float | None = None) -> str:
        if self.messages:
            return self.messages.pop(0)
        self._advance(1500)
        raise TimeoutError("no message")

    def close(self) -> None:
        self.closed = True


if __name__ == "__main__":
    unittest.main()
