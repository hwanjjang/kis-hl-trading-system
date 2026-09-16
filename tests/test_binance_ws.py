from __future__ import annotations

import json
import unittest
from decimal import Decimal

from kis_hl.binance.client import BinanceFuturesClient
from kis_hl.binance.ws import (
    BinanceMarketStreamClient,
    BinanceUserStreamClient,
    agg_trade_stream,
    book_ticker_stream,
    kline_stream,
    mark_price_stream,
    market_stream_url,
    parse_market_ticks,
    parse_order_event,
    stream_route,
    user_stream_url,
)
from kis_hl.config import BinanceConfig


def make_config() -> BinanceConfig:
    return BinanceConfig(
        base_url="https://fapi.example.test",
        ws_market_url="wss://fstream.example.test/market",
        ws_public_url="wss://fstream.example.test/public",
        ws_user_url="wss://fstream.example.test/private",
        api_key="k",
        api_secret="s",
        key_profile="default",
    )


class ScriptedTransport:
    """Yields scripted frames, then raises TimeoutError forever (idle path)."""

    def __init__(self, frames: list[str], *, advance: callable = None) -> None:
        self.frames = list(frames)
        self.sent: list[str] = []
        self.closed = False
        self.advance = advance

    def send_text(self, text: str) -> None:
        self.sent.append(text)

    def recv_text(self, *, timeout_seconds: float | None = None) -> str:
        if self.advance:
            self.advance(int((timeout_seconds or 1) * 1000))
        if self.frames:
            return self.frames.pop(0)
        raise TimeoutError()

    def close(self) -> None:
        self.closed = True


class StreamNameTests(unittest.TestCase):
    def test_stream_names_are_lowercase(self) -> None:
        self.assertEqual(mark_price_stream("BTCUSDT"), "btcusdt@markPrice")
        self.assertEqual(mark_price_stream("BTCUSDT", fast=True), "btcusdt@markPrice@1s")
        self.assertEqual(book_ticker_stream("BTCUSDT"), "btcusdt@bookTicker")
        self.assertEqual(kline_stream("BTCUSDT", "1h"), "btcusdt@kline_1h")
        self.assertEqual(agg_trade_stream("BTCUSDT"), "btcusdt@aggTrade")

    def test_kline_stream_rejects_bad_interval(self) -> None:
        with self.assertRaises(ValueError):
            kline_stream("BTCUSDT", "3h")

    def test_market_stream_url_uses_combined_stream_form_per_route(self) -> None:
        url = market_stream_url(make_config(), ["btcusdt@markPrice@1s", "btcusdt@aggTrade"])
        self.assertEqual(url, "wss://fstream.example.test/market/stream?streams=btcusdt@markPrice@1s/btcusdt@aggTrade")
        url = market_stream_url(make_config(), ["btcusdt@bookTicker"])
        self.assertEqual(url, "wss://fstream.example.test/public/stream?streams=btcusdt@bookTicker")

    def test_market_stream_url_rejects_mixed_routes(self) -> None:
        self.assertEqual(stream_route("btcusdt@bookTicker"), "public")
        self.assertEqual(stream_route("btcusdt@depth5@100ms"), "public")
        self.assertEqual(stream_route("btcusdt@markPrice@1s"), "market")
        with self.assertRaises(ValueError) as ctx:
            market_stream_url(make_config(), ["btcusdt@markPrice@1s", "btcusdt@bookTicker"])
        self.assertIn("/public", str(ctx.exception))

    def test_market_stream_url_requires_streams(self) -> None:
        with self.assertRaises(ValueError):
            market_stream_url(make_config(), [])

    def test_user_stream_url(self) -> None:
        self.assertEqual(user_stream_url(make_config(), "abc"), "wss://fstream.example.test/private/ws/abc")


class MarketTickParserTests(unittest.TestCase):
    def test_parses_mark_price_from_combined_envelope(self) -> None:
        payload = {
            "stream": "btcusdt@markPrice@1s",
            "data": {"e": "markPriceUpdate", "E": 1700000000123, "s": "BTCUSDT", "p": "75849.80", "i": "75883.56", "r": "0.0001", "T": 1700003600000},
        }
        ticks = parse_market_ticks(payload, received_at_ms=5)
        self.assertEqual(len(ticks), 1)
        tick = ticks[0]
        self.assertEqual(tick.source, "binance")
        self.assertEqual(tick.symbol, "BTCUSDT")
        self.assertEqual(tick.price, Decimal("75849.80"))
        self.assertEqual(tick.event_time, 1700000000123)
        self.assertEqual(tick.received_at_ms, 5)
        self.assertEqual(tick.raw["kind"], "mark_price")
        self.assertEqual(tick.raw["funding_rate"], "0.0001")

    def test_parses_book_ticker_as_mid_with_raw_quotes(self) -> None:
        payload = {"e": "bookTicker", "u": 1, "s": "BTCUSDT", "b": "100.0", "B": "1", "a": "100.2", "A": "2", "T": 7, "E": 8}
        ticks = parse_market_ticks(payload, received_at_ms=9)
        self.assertEqual(ticks[0].price, Decimal("100.1"))
        self.assertEqual(ticks[0].raw["kind"], "book_ticker")
        self.assertEqual(ticks[0].raw["bid"], "100.0")
        self.assertEqual(ticks[0].raw["ask"], "100.2")

    def test_parses_kline_close_and_volume(self) -> None:
        payload = {"e": "kline", "E": 3, "s": "BTCUSDT", "k": {"t": 1, "T": 2, "i": "1h", "o": "1", "h": "3", "l": "0.5", "c": "2.5", "v": "10", "x": False}}
        ticks = parse_market_ticks(payload, received_at_ms=4)
        self.assertEqual(ticks[0].price, Decimal("2.5"))
        self.assertEqual(ticks[0].size, Decimal("10"))
        self.assertEqual(ticks[0].raw["kind"], "kline")
        self.assertEqual(ticks[0].raw["interval"], "1h")
        self.assertFalse(ticks[0].raw["closed"])

    def test_parses_agg_trade(self) -> None:
        payload = {"e": "aggTrade", "E": 3, "s": "BTCUSDT", "a": 1, "p": "2.0", "q": "0.5", "T": 2, "m": True}
        ticks = parse_market_ticks(payload, received_at_ms=4)
        self.assertEqual(ticks[0].price, Decimal("2.0"))
        self.assertEqual(ticks[0].size, Decimal("0.5"))
        self.assertEqual(ticks[0].raw["kind"], "agg_trade")

    def test_skips_unknown_and_unparsable(self) -> None:
        self.assertEqual(parse_market_ticks({"e": "other"}, received_at_ms=1), [])
        self.assertEqual(parse_market_ticks({"e": "markPriceUpdate", "s": "X", "p": "nope"}, received_at_ms=1), [])
        self.assertEqual(parse_market_ticks(["not", "dict"], received_at_ms=1), [])


class MarketStreamClientTests(unittest.TestCase):
    def test_market_client_connects_to_combined_url_and_delivers_dicts(self) -> None:
        urls: list[str] = []
        frame = json.dumps({"stream": "btcusdt@bookTicker", "data": {"e": "bookTicker", "s": "BTCUSDT", "b": "1", "a": "3", "B": "1", "A": "1"}})
        received: list[dict] = []

        def factory(url: str, _timeout: float) -> ScriptedTransport:
            urls.append(url)
            return ScriptedTransport([frame, "not json"])

        client = BinanceMarketStreamClient(
            make_config(),
            streams=["btcusdt@bookTicker"],
            on_message=received.append,
            transport_factory=factory,
        )
        status = client.run(max_messages=2)
        self.assertEqual(urls, ["wss://fstream.example.test/public/stream?streams=btcusdt@bookTicker"])
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["stream"], "btcusdt@bookTicker")
        self.assertEqual(status.connection_count, 1)


class OrderEventParserTests(unittest.TestCase):
    ORDER_UPDATE = {
        "e": "ORDER_TRADE_UPDATE",
        "E": 1700000000500,
        "T": 1700000000400,
        "o": {
            "s": "BTCUSDT", "c": "cli-1", "S": "BUY", "o": "LIMIT", "f": "GTC",
            "q": "0.010", "p": "75000.0", "ap": "74990.5", "sp": "0", "x": "TRADE",
            "X": "PARTIALLY_FILLED", "i": 123456, "l": "0.004", "z": "0.004", "L": "74990.5",
            "N": "USDT", "n": "0.01", "T": 1700000000400, "t": 99, "R": False, "rp": "0",
        },
    }

    def test_parses_order_trade_update(self) -> None:
        event = parse_order_event(self.ORDER_UPDATE, received_at_ms=7)
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.venue, "binance")
        self.assertEqual(event.symbol, "BTCUSDT")
        self.assertEqual(event.order_id, "123456")
        self.assertEqual(event.client_order_id, "cli-1")
        self.assertEqual(event.side, "BUY")
        self.assertEqual(event.order_type, "LIMIT")
        self.assertEqual(event.execution_type, "TRADE")
        self.assertEqual(event.status, "PARTIALLY_FILLED")
        self.assertEqual(event.price, Decimal("75000.0"))
        self.assertEqual(event.avg_price, Decimal("74990.5"))
        self.assertEqual(event.orig_qty, Decimal("0.010"))
        self.assertEqual(event.last_filled_qty, Decimal("0.004"))
        self.assertEqual(event.cum_filled_qty, Decimal("0.004"))
        self.assertEqual(event.stop_price, Decimal("0"))
        self.assertFalse(event.reduce_only)
        self.assertEqual(event.event_time_ms, 1700000000500)
        self.assertEqual(event.received_at_ms, 7)
        self.assertEqual(event.raw["e"], "ORDER_TRADE_UPDATE")

    def test_ignores_non_order_events(self) -> None:
        self.assertIsNone(parse_order_event({"e": "ACCOUNT_UPDATE", "a": {}}, received_at_ms=1))
        self.assertIsNone(parse_order_event({"e": "ORDER_TRADE_UPDATE"}, received_at_ms=1))


class UserStreamClientTests(unittest.TestCase):
    def _make_client(self, keys: list[str]) -> tuple[BinanceFuturesClient, list[str]]:
        calls: list[str] = []

        class FakeRest(BinanceFuturesClient):
            def create_listen_key(self_inner) -> str:  # noqa: N805
                calls.append("create")
                return keys.pop(0)

            def keepalive_listen_key(self_inner) -> None:  # noqa: N805
                calls.append("keepalive")

            def close_listen_key(self_inner) -> None:  # noqa: N805
                calls.append("close")

        return FakeRest(make_config()), calls

    def test_user_client_creates_listen_key_per_connection_and_reconnects_on_expiry(self) -> None:
        now_ms = 0
        urls: list[str] = []
        received: list[dict] = []

        def advance(ms: int) -> None:
            nonlocal now_ms
            now_ms += ms

        expired = json.dumps({"e": "listenKeyExpired", "E": 1})
        order = json.dumps(OrderEventParserTests.ORDER_UPDATE)
        scripts = [[expired], [order]]

        def factory(url: str, _timeout: float) -> ScriptedTransport:
            urls.append(url)
            return ScriptedTransport(scripts.pop(0), advance=advance)

        rest, calls = self._make_client(["key-a", "key-b"])
        client = BinanceUserStreamClient(
            make_config(),
            rest,
            on_message=received.append,
            transport_factory=factory,
            now_ms=lambda: now_ms,
            sleep=lambda seconds: advance(int(seconds * 1000)),
            reconnect_min_delay_ms=10,
            reconnect_max_delay_ms=10,
        )
        status = client.run(max_messages=1, max_reconnects=1)
        self.assertEqual(urls, [
            "wss://fstream.example.test/private/ws/key-a",
            "wss://fstream.example.test/private/ws/key-b",
        ])
        self.assertEqual(calls[:2], ["create", "create"])
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["e"], "ORDER_TRADE_UPDATE")
        self.assertEqual(status.reconnect_count, 1)
        self.assertIn("listenKeyExpired", str(status.last_error))

    def test_user_client_sends_keepalive_when_interval_elapses(self) -> None:
        now_ms = 0

        def advance(ms: int) -> None:
            nonlocal now_ms
            now_ms += ms

        def factory(_url: str, _timeout: float) -> ScriptedTransport:
            return ScriptedTransport([], advance=advance)

        rest, calls = self._make_client(["key-a"])
        client = BinanceUserStreamClient(
            make_config(),
            rest,
            on_message=lambda _payload: None,
            transport_factory=factory,
            now_ms=lambda: now_ms,
            sleep=lambda seconds: advance(int(seconds * 1000)),
            keepalive_interval_ms=2_000,
            stale_after_ms=5_000,
            recv_timeout_seconds=1,
        )
        client.run(max_reconnects=0)
        self.assertEqual(calls[0], "create")
        self.assertIn("keepalive", calls)
        self.assertGreaterEqual(calls.count("keepalive"), 1)


if __name__ == "__main__":
    unittest.main()
