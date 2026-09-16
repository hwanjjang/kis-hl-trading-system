from __future__ import annotations

import json
import unittest
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

from kis_hl.binance.client import BinanceFuturesClient, KLINE_INTERVALS, sign_query
from kis_hl.config import BinanceConfig


def make_config(**overrides: str) -> BinanceConfig:
    values = {
        "base_url": "https://fapi.example.test",
        "ws_market_url": "wss://fstream.example.test/market",
        "ws_public_url": "wss://fstream.example.test/public",
        "ws_user_url": "wss://fstream.example.test/private",
        "api_key": "test-api-key",
        "api_secret": "test-api-secret",
        "key_profile": "default",
        "recv_window_ms": 5000,
    }
    values.update(overrides)
    return BinanceConfig(**values)  # type: ignore[arg-type]


class RecordingClient(BinanceFuturesClient):
    def __init__(self, config: BinanceConfig, responses: list[tuple[int, str]] | None = None) -> None:
        super().__init__(config, now_ms=lambda: 1_700_000_000_000)
        self.calls: list[dict[str, object]] = []
        self.responses = list(responses or [(200, "{}")])

    def send(self, method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, dict[str, str], str]:
        self.calls.append({"method": method, "url": url, "headers": headers, "body": body})
        status, text = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        return status, {"x-mbx-used-weight-1m": "5"}, text


class BinanceSigningTests(unittest.TestCase):
    def test_sign_query_matches_known_hmac_sha256_vector(self) -> None:
        # Vector from the Binance signed-endpoint example (secret and query are documentation samples).
        secret = "NhqPtmdSJYdKjVHjA7PZj4Mge3R5YNiP1e3UZjInClVN65XAbvqqM6A7H5fATj0j"
        query = (
            "symbol=LTCBTC&side=BUY&type=LIMIT&timeInForce=GTC&quantity=1&price=0.1"
            "&recvWindow=5000&timestamp=1499827319559"
        )
        self.assertEqual(
            sign_query(secret, query),
            "c8db56825ae71d6d79447849e617115f4a920fa2acdcab2b053c4b2838bd6b71",
        )


class BinancePublicRequestTests(unittest.TestCase):
    def test_public_get_has_no_api_key_header_and_builds_query(self) -> None:
        client = RecordingClient(make_config(), [(200, '{"symbol": "BTCUSDT", "markPrice": "1.5"}')])
        payload = client.premium_index("btcusdt")
        self.assertEqual(payload["markPrice"], "1.5")
        call = client.calls[0]
        self.assertEqual(call["method"], "GET")
        self.assertEqual(call["url"], "https://fapi.example.test/fapi/v1/premiumIndex?symbol=BTCUSDT")
        self.assertNotIn("X-MBX-APIKEY", call["headers"])

    def test_public_get_works_without_credentials(self) -> None:
        client = RecordingClient(make_config(api_key="", api_secret=""), [(200, '{"serverTime": 5}')])
        self.assertEqual(client.server_time(), 5)

    def test_http_error_surfaces_binance_code_and_message(self) -> None:
        client = RecordingClient(make_config(), [(400, '{"code": -1120, "msg": "Invalid interval."}')])
        with self.assertRaises(RuntimeError) as ctx:
            client.book_ticker("BTCUSDT")
        self.assertIn("-1120", str(ctx.exception))
        self.assertIn("Invalid interval.", str(ctx.exception))

    def test_klines_rejects_unknown_interval_before_sending(self) -> None:
        client = RecordingClient(make_config())
        with self.assertRaises(ValueError):
            client.klines("BTCUSDT", "3h")
        self.assertEqual(client.calls, [])
        self.assertIn("1h", KLINE_INTERVALS)

    def test_klines_normalizes_rows(self) -> None:
        raw = json.dumps(
            [
                [1, "10.0", "12.0", "9.5", "11.0", "3.5", 2, "38.5", 4, "1.0", "11.0", "0"],
            ]
        )
        client = RecordingClient(make_config(), [(200, raw)])
        candles = client.klines("BTCUSDT", "1h", limit=1, start_time_ms=100, end_time_ms=200)
        self.assertEqual(candles[0]["t"], 1)
        self.assertEqual(candles[0]["T"], 2)
        self.assertEqual(candles[0]["h"], Decimal("12.0"))
        self.assertEqual(candles[0]["c"], Decimal("11.0"))
        self.assertEqual(candles[0]["v"], Decimal("3.5"))
        query = parse_qs(urlsplit(str(client.calls[0]["url"])).query)
        self.assertEqual(query["interval"], ["1h"])
        self.assertEqual(query["limit"], ["1"])
        self.assertEqual(query["startTime"], ["100"])
        self.assertEqual(query["endTime"], ["200"])

    def test_symbol_filters_normalizes_exchange_info(self) -> None:
        raw = json.dumps(
            {
                "symbols": [
                    {
                        "symbol": "BTCUSDT",
                        "status": "TRADING",
                        "contractType": "PERPETUAL",
                        "pricePrecision": 2,
                        "quantityPrecision": 3,
                        "orderTypes": ["LIMIT", "TRAILING_STOP_MARKET"],
                        "timeInForce": ["GTC", "IOC"],
                        "filters": [
                            {"filterType": "PRICE_FILTER", "tickSize": "0.10", "minPrice": "556.80", "maxPrice": "4529764"},
                            {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001", "maxQty": "1000"},
                            {"filterType": "MIN_NOTIONAL", "notional": "50"},
                        ],
                    }
                ]
            }
        )
        client = RecordingClient(make_config(), [(200, raw)])
        filters = client.symbol_filters("BTCUSDT")
        self.assertEqual(filters["tick_size"], Decimal("0.10"))
        self.assertEqual(filters["step_size"], Decimal("0.001"))
        self.assertEqual(filters["min_qty"], Decimal("0.001"))
        self.assertEqual(filters["min_notional"], Decimal("50"))
        self.assertEqual(filters["price_precision"], 2)
        self.assertEqual(filters["quantity_precision"], 3)
        self.assertIn("TRAILING_STOP_MARKET", filters["order_types"])
        self.assertEqual(filters["status"], "TRADING")

    def test_symbol_filters_raises_for_unknown_symbol(self) -> None:
        client = RecordingClient(make_config(), [(200, '{"symbols": []}')])
        with self.assertRaises(RuntimeError):
            client.symbol_filters("NOPEUSDT")


class BinanceSignedRequestTests(unittest.TestCase):
    def test_signed_get_appends_timestamp_recv_window_and_signature(self) -> None:
        client = RecordingClient(make_config(), [(200, "[]")])
        client.open_orders("BTCUSDT")
        call = client.calls[0]
        self.assertEqual(call["headers"]["X-MBX-APIKEY"], "test-api-key")
        split = urlsplit(str(call["url"]))
        self.assertEqual(split.path, "/fapi/v1/openOrders")
        query = split.query
        unsigned, _, signature = query.rpartition("&signature=")
        self.assertEqual(unsigned, "symbol=BTCUSDT&recvWindow=5000&timestamp=1700000000000")
        self.assertEqual(signature, sign_query("test-api-secret", unsigned))

    def test_signed_get_fails_closed_without_credentials(self) -> None:
        client = RecordingClient(make_config(api_key="", api_secret=""))
        with self.assertRaises(RuntimeError) as ctx:
            client.account()
        self.assertIn("credentials", str(ctx.exception).lower())
        self.assertEqual(client.calls, [])

    def test_order_status_requires_an_identifier(self) -> None:
        client = RecordingClient(make_config())
        with self.assertRaises(ValueError):
            client.order_status("BTCUSDT")
        self.assertEqual(client.calls, [])

    def test_order_status_uses_client_order_id_when_given(self) -> None:
        client = RecordingClient(make_config(), [(200, "{}")])
        client.order_status("BTCUSDT", client_order_id="abc")
        query = parse_qs(urlsplit(str(client.calls[0]["url"])).query)
        self.assertEqual(query["origClientOrderId"], ["abc"])
        self.assertNotIn("orderId", query)


class BinanceListenKeyTests(unittest.TestCase):
    def test_create_listen_key_posts_with_api_key_header_and_no_signature(self) -> None:
        client = RecordingClient(make_config(), [(200, '{"listenKey": "key-123"}')])
        self.assertEqual(client.create_listen_key(), "key-123")
        call = client.calls[0]
        self.assertEqual(call["method"], "POST")
        self.assertEqual(call["url"], "https://fapi.example.test/fapi/v1/listenKey")
        self.assertEqual(call["headers"]["X-MBX-APIKEY"], "test-api-key")
        self.assertNotIn("signature", call["url"])

    def test_keepalive_and_close_use_put_and_delete(self) -> None:
        client = RecordingClient(make_config(), [(200, "{}")])
        client.keepalive_listen_key()
        client.close_listen_key()
        self.assertEqual([call["method"] for call in client.calls], ["PUT", "DELETE"])

    def test_listen_key_requires_api_key_only(self) -> None:
        client = RecordingClient(make_config(api_secret=""), [(200, '{"listenKey": "k"}')])
        self.assertEqual(client.create_listen_key(), "k")
        no_key = RecordingClient(make_config(api_key=""))
        with self.assertRaises(RuntimeError):
            no_key.create_listen_key()


if __name__ == "__main__":
    unittest.main()
