from __future__ import annotations

import json
import unittest
from decimal import ROUND_DOWN, ROUND_UP, Decimal
from urllib.parse import parse_qs, urlsplit

from kis_hl.binance.trading import (
    BinanceOrderSubmission,
    BinanceTradingClient,
    extract_binance_order_id,
    round_to_step,
    submission_to_dict,
)
from kis_hl.config import BinanceConfig

FILTERS = {
    "symbol": "BTCUSDT",
    "status": "TRADING",
    "tick_size": Decimal("0.10"),
    "step_size": Decimal("0.001"),
    "min_qty": Decimal("0.001"),
    "max_qty": Decimal("1000"),
    "market_max_qty": Decimal("120"),
    "min_notional": Decimal("50"),
    "price_precision": 2,
    "quantity_precision": 3,
    "order_types": ["LIMIT", "MARKET", "STOP_MARKET", "TRAILING_STOP_MARKET"],
    "time_in_force": ["GTC", "IOC", "FOK", "GTX"],
}
MARK = Decimal("76000")

EXCHANGE_INFO = json.dumps(
    {
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "status": "TRADING",
                "pricePrecision": 2,
                "quantityPrecision": 3,
                "orderTypes": ["LIMIT", "MARKET", "STOP_MARKET", "TRAILING_STOP_MARKET"],
                "timeInForce": ["GTC", "IOC", "FOK", "GTX"],
                "filters": [
                    {"filterType": "PRICE_FILTER", "tickSize": "0.10", "minPrice": "556.80", "maxPrice": "4529764"},
                    {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001", "maxQty": "1000"},
                    {"filterType": "MARKET_LOT_SIZE", "stepSize": "0.001", "minQty": "0.001", "maxQty": "120"},
                    {"filterType": "MIN_NOTIONAL", "notional": "50"},
                ],
            }
        ]
    }
)
PREMIUM = json.dumps({"symbol": "BTCUSDT", "markPrice": "76000.00000000"})
ONE_WAY = json.dumps({"dualSidePosition": False})
HEDGE = json.dumps({"dualSidePosition": True})
ACK = json.dumps({"orderId": 123, "clientOrderId": "kh-abc", "status": "NEW", "symbol": "BTCUSDT"})


def make_config(**overrides: object) -> BinanceConfig:
    values: dict[str, object] = {
        "base_url": "https://fapi.example.test",
        "ws_market_url": "wss://fstream.example.test/market",
        "ws_public_url": "wss://fstream.example.test/public",
        "ws_user_url": "wss://fstream.example.test/private",
        "api_key": "test-api-key",
        "api_secret": "test-api-secret",
        "key_profile": "default",
        "recv_window_ms": 5000,
        "live_symbols": ("BTCUSDT",),
    }
    values.update(overrides)
    return BinanceConfig(**values)  # type: ignore[arg-type]


class RecordingTradingClient(BinanceTradingClient):
    """Replays canned responses keyed by path so guard order is observable."""

    def __init__(self, config: BinanceConfig, responses: dict[str, tuple[int, str]] | None = None) -> None:
        super().__init__(config, now_ms=lambda: 1_700_000_000_000)
        self.calls: list[dict[str, object]] = []
        self.responses = dict(responses or {})

    def send(self, method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, dict[str, str], str]:
        path = urlsplit(url).path
        self.calls.append({"method": method, "path": path, "query": parse_qs(urlsplit(url).query), "headers": headers})
        status, text = self.responses.get(path, (200, "{}"))
        return status, {}, text

    def paths(self) -> list[str]:
        return [f"{c['method']} {c['path']}" for c in self.calls]


class RoundingTests(unittest.TestCase):
    def test_round_to_step_down_and_up(self) -> None:
        self.assertEqual(round_to_step(Decimal("0.0019"), Decimal("0.001")), Decimal("0.001"))
        self.assertEqual(round_to_step(Decimal("76000.04"), Decimal("0.10")), Decimal("76000.0"))
        self.assertEqual(round_to_step(Decimal("76000.04"), Decimal("0.10"), rounding=ROUND_UP), Decimal("76000.1"))
        with self.assertRaises(ValueError):
            round_to_step(Decimal("1"), Decimal("0"))


class PlaceOrderDryRunTests(unittest.TestCase):
    def test_market_dry_run_builds_rounded_request_without_network(self) -> None:
        client = RecordingTradingClient(make_config(api_key="", api_secret=""))
        submission = client.place_order(
            symbol="btcusdt", side="buy", order_type="market", quantity=Decimal("0.0019"),
            filters=FILTERS, mark_price=MARK,
        )
        self.assertIsInstance(submission, BinanceOrderSubmission)
        self.assertEqual(submission.status, "dry_run")
        self.assertTrue(submission.dry_run)
        self.assertEqual(submission.symbol, "BTCUSDT")
        params = submission.request["params"]
        self.assertEqual(params["type"], "MARKET")
        self.assertEqual(params["side"], "BUY")
        self.assertEqual(params["quantity"], "0.001")
        self.assertNotIn("price", params)
        self.assertNotIn("reduceOnly", params)
        self.assertEqual(params["newOrderRespType"], "RESULT")
        self.assertRegex(params["newClientOrderId"], r"^[A-Za-z0-9._:/-]{1,36}$")
        self.assertEqual(submission.request["path"], "/fapi/v1/order")
        self.assertEqual(client.calls, [])

    def test_limit_requires_price_and_rounds_by_side(self) -> None:
        client = RecordingTradingClient(make_config())
        with self.assertRaises(ValueError):
            client.place_order(symbol="BTCUSDT", side="BUY", order_type="LIMIT", quantity=Decimal("0.01"), filters=FILTERS)
        buy = client.place_order(
            symbol="BTCUSDT", side="BUY", order_type="LIMIT", quantity=Decimal("0.01"), price=Decimal("75000.07"), filters=FILTERS,
        )
        self.assertEqual(buy.request["params"]["price"], "75000.00")
        self.assertEqual(buy.request["params"]["timeInForce"], "GTC")
        sell = client.place_order(
            symbol="BTCUSDT", side="SELL", order_type="LIMIT", quantity=Decimal("0.01"), price=Decimal("75000.01"),
            tif="GTX", reduce_only=True, client_order_id="my-order-1", filters=FILTERS,
        )
        self.assertEqual(sell.request["params"]["price"], "75000.10")
        self.assertEqual(sell.request["params"]["timeInForce"], "GTX")
        self.assertEqual(sell.request["params"]["reduceOnly"], "true")
        self.assertEqual(sell.request["params"]["newClientOrderId"], "my-order-1")

    def test_filter_violations_are_rejected_before_any_call(self) -> None:
        client = RecordingTradingClient(make_config())
        with self.assertRaises(ValueError) as too_small:
            client.place_order(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0.0005"), filters=FILTERS, mark_price=MARK)
        self.assertIn("minQty", str(too_small.exception))
        with self.assertRaises(ValueError) as notional:
            client.place_order(symbol="BTCUSDT", side="BUY", order_type="LIMIT", quantity=Decimal("0.001"), price=Decimal("10"), filters=FILTERS)
        self.assertIn("MIN_NOTIONAL", str(notional.exception))
        with self.assertRaises(ValueError) as too_big:
            client.place_order(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("121"), filters=FILTERS, mark_price=MARK)
        self.assertIn("maxQty", str(too_big.exception))
        with self.assertRaises(ValueError):
            client.place_order(symbol="BTCUSDT", side="HOLD", order_type="MARKET", quantity=Decimal("1"), filters=FILTERS, mark_price=MARK)
        with self.assertRaises(ValueError):
            client.place_order(symbol="BTCUSDT", side="BUY", order_type="LIMIT", quantity=Decimal("1"), price=Decimal("1"), tif="DAY", filters=FILTERS)
        with self.assertRaises(ValueError):
            client.place_order(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("1"), client_order_id="bad id!", filters=FILTERS, mark_price=MARK)
        self.assertEqual(client.calls, [])

    def test_dry_run_fetches_public_filters_and_mark_when_not_injected(self) -> None:
        client = RecordingTradingClient(
            make_config(api_key="", api_secret=""),
            {"/fapi/v1/exchangeInfo": (200, EXCHANGE_INFO), "/fapi/v1/premiumIndex": (200, PREMIUM)},
        )
        submission = client.place_order(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0.002"))
        self.assertEqual(submission.status, "dry_run")
        self.assertEqual(client.paths(), ["GET /fapi/v1/exchangeInfo", "GET /fapi/v1/premiumIndex"])
        for call in client.calls:
            self.assertNotIn("X-MBX-APIKEY", call["headers"])


class LiveGuardTests(unittest.TestCase):
    def test_live_rejects_symbol_outside_allowlist_before_credentials(self) -> None:
        client = RecordingTradingClient(make_config(api_key="", api_secret="", live_symbols=("BTCUSDT",)))
        eth_filters = dict(FILTERS, symbol="ETHUSDT")
        with self.assertRaises(RuntimeError) as ctx:
            client.place_order(symbol="ETHUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0.02"), filters=eth_filters, mark_price=Decimal("3000"), dry_run=False)
        self.assertIn("BINANCE_LIVE_SYMBOLS", str(ctx.exception))
        self.assertEqual(client.calls, [])

    def test_live_requires_credentials_before_position_mode_call(self) -> None:
        client = RecordingTradingClient(make_config(api_key="", api_secret=""))
        with self.assertRaises(RuntimeError) as ctx:
            client.place_order(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0.01"), filters=FILTERS, mark_price=MARK, dry_run=False)
        self.assertIn("credentials", str(ctx.exception).lower())
        self.assertEqual(client.calls, [])

    def test_live_rejects_hedge_mode_before_posting(self) -> None:
        client = RecordingTradingClient(make_config(), {"/fapi/v1/positionSide/dual": (200, HEDGE)})
        with self.assertRaises(RuntimeError) as ctx:
            client.place_order(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0.01"), filters=FILTERS, mark_price=MARK, dry_run=False)
        self.assertIn("hedge", str(ctx.exception).lower())
        self.assertEqual(client.paths(), ["GET /fapi/v1/positionSide/dual"])

    def test_live_fails_closed_when_position_mode_is_not_explicit(self) -> None:
        for body in ("{}", "[]", "null", ""):
            client = RecordingTradingClient(make_config(), {"/fapi/v1/positionSide/dual": (200, body)})
            with self.assertRaises(RuntimeError) as ctx:
                client.place_order(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0.01"), filters=FILTERS, mark_price=MARK, dry_run=False)
            self.assertIn("position mode", str(ctx.exception))
            self.assertEqual(client.paths(), ["GET /fapi/v1/positionSide/dual"])

    def test_non_finite_inputs_and_newline_ids_are_rejected(self) -> None:
        client = RecordingTradingClient(make_config())
        for bad in (Decimal("NaN"), Decimal("Infinity")):
            with self.assertRaises(ValueError):
                client.place_order(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=bad, filters=FILTERS, mark_price=MARK)
        with self.assertRaises(ValueError):
            client.place_order(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0.01"), client_order_id="abc\n", filters=FILTERS, mark_price=MARK)
        with self.assertRaises(ValueError):
            client.place_stop_market(symbol="BTCUSDT", side="SELL", stop_price=Decimal("74000"), quantity=Decimal("0.01"), close_position=True, filters=FILTERS, mark_price=MARK)
        self.assertEqual(client.calls, [])

    def test_live_market_order_posts_signed_query_and_returns_ack(self) -> None:
        client = RecordingTradingClient(make_config(), {"/fapi/v1/positionSide/dual": (200, ONE_WAY), "/fapi/v1/order": (200, ACK)})
        submission = client.place_order(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0.01"), filters=FILTERS, mark_price=MARK, dry_run=False)
        self.assertEqual(submission.status, "submitted")
        self.assertFalse(submission.dry_run)
        self.assertEqual(client.paths(), ["GET /fapi/v1/positionSide/dual", "POST /fapi/v1/order"])
        post = client.calls[-1]
        self.assertEqual(post["headers"]["X-MBX-APIKEY"], "test-api-key")
        query = post["query"]
        self.assertEqual(query["symbol"], ["BTCUSDT"])
        self.assertEqual(query["type"], ["MARKET"])
        self.assertEqual(query["quantity"], ["0.010"])
        self.assertIn("signature", query)
        self.assertIn("timestamp", query)
        self.assertEqual(submission.response["orderId"], 123)
        self.assertEqual(extract_binance_order_id(submission.response), "123")
        as_dict = submission_to_dict(submission)
        self.assertEqual(as_dict["status"], "submitted")
        self.assertIn("submitted_at_ms", as_dict)

    def test_live_exchange_error_becomes_rejected_submission(self) -> None:
        client = RecordingTradingClient(
            make_config(),
            {"/fapi/v1/positionSide/dual": (200, ONE_WAY), "/fapi/v1/order": (400, json.dumps({"code": -2021, "msg": "Order would immediately trigger."}))},
        )
        submission = client.place_order(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0.01"), filters=FILTERS, mark_price=MARK, dry_run=False)
        self.assertEqual(submission.status, "rejected")
        self.assertIn("-2021", submission.response["error"])

    def test_exchange_test_posts_to_test_endpoint_without_allowlist_or_position_mode(self) -> None:
        client = RecordingTradingClient(make_config(live_symbols=("ETHUSDT",)), {"/fapi/v1/order/test": (200, "{}")})
        submission = client.place_order(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0.01"), filters=FILTERS, mark_price=MARK, exchange_test=True)
        self.assertEqual(submission.status, "exchange_test")
        self.assertTrue(submission.dry_run)
        self.assertEqual(client.paths(), ["POST /fapi/v1/order/test"])
        self.assertEqual(client.calls[0]["headers"]["X-MBX-APIKEY"], "test-api-key")

    def test_exchange_test_error_becomes_rejected_submission(self) -> None:
        client = RecordingTradingClient(
            make_config(), {"/fapi/v1/order/test": (401, json.dumps({"code": -2015, "msg": "Invalid API-key, IP, or permissions for action"}))}
        )
        submission = client.place_order(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0.01"), filters=FILTERS, mark_price=MARK, exchange_test=True)
        self.assertEqual(submission.status, "rejected")
        self.assertTrue(submission.dry_run)
        self.assertIn("-2015", submission.response["error"])

    def test_exchange_test_requires_credentials(self) -> None:
        client = RecordingTradingClient(make_config(api_key="", api_secret=""))
        with self.assertRaises(RuntimeError):
            client.place_order(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0.01"), filters=FILTERS, mark_price=MARK, exchange_test=True)
        self.assertEqual(client.calls, [])


class StopMarketTests(unittest.TestCase):
    def test_close_position_stop_has_no_quantity_or_reduce_only(self) -> None:
        client = RecordingTradingClient(make_config())
        submission = client.place_stop_market(symbol="BTCUSDT", side="SELL", stop_price=Decimal("74000.04"), filters=FILTERS, mark_price=MARK)
        params = submission.request["params"]
        self.assertEqual(params["type"], "STOP_MARKET")
        self.assertEqual(params["closePosition"], "true")
        self.assertEqual(params["stopPrice"], "74000.10")  # SELL stop rounds up: triggers earlier
        self.assertEqual(params["workingType"], "MARK_PRICE")
        self.assertNotIn("quantity", params)
        self.assertNotIn("reduceOnly", params)

    def test_reduce_only_stop_requires_quantity_and_rounds(self) -> None:
        client = RecordingTradingClient(make_config())
        with self.assertRaises(ValueError):
            client.place_stop_market(symbol="BTCUSDT", side="SELL", stop_price=Decimal("74000"), close_position=False, filters=FILTERS, mark_price=MARK)
        submission = client.place_stop_market(
            symbol="BTCUSDT", side="BUY", stop_price=Decimal("78000.01"), close_position=False, quantity=Decimal("0.0104"),
            working_type="CONTRACT_PRICE", filters=FILTERS, mark_price=MARK,
        )
        params = submission.request["params"]
        self.assertEqual(params["reduceOnly"], "true")
        self.assertEqual(params["quantity"], "0.010")
        self.assertEqual(params["stopPrice"], "78000.00")  # BUY stop rounds down: triggers earlier
        self.assertEqual(params["workingType"], "CONTRACT_PRICE")
        self.assertNotIn("closePosition", params)

    def test_stop_direction_is_validated_against_mark_price(self) -> None:
        client = RecordingTradingClient(make_config())
        with self.assertRaises(ValueError) as sell_above:
            client.place_stop_market(symbol="BTCUSDT", side="SELL", stop_price=Decimal("77000"), filters=FILTERS, mark_price=MARK)
        self.assertIn("below", str(sell_above.exception))
        with self.assertRaises(ValueError):
            client.place_stop_market(symbol="BTCUSDT", side="BUY", stop_price=Decimal("75000"), filters=FILTERS, mark_price=MARK)


class TrailingStopTests(unittest.TestCase):
    def test_trailing_stop_params_and_callback_bounds(self) -> None:
        client = RecordingTradingClient(make_config())
        submission = client.place_trailing_stop(
            symbol="BTCUSDT", side="SELL", quantity=Decimal("0.0105"), callback_rate=Decimal("1.5"),
            activation_price=Decimal("77000.04"), filters=FILTERS, mark_price=MARK,
        )
        params = submission.request["params"]
        self.assertEqual(params["type"], "TRAILING_STOP_MARKET")
        self.assertEqual(params["callbackRate"], "1.5")
        self.assertEqual(params["activationPrice"], "77000.10")
        self.assertEqual(params["quantity"], "0.010")
        self.assertEqual(params["reduceOnly"], "true")
        self.assertEqual(params["workingType"], "MARK_PRICE")
        no_activation = client.place_trailing_stop(symbol="BTCUSDT", side="SELL", quantity=Decimal("0.01"), callback_rate=Decimal("2"), filters=FILTERS, mark_price=MARK)
        self.assertNotIn("activationPrice", no_activation.request["params"])
        for bad in (Decimal("0.05"), Decimal("10.1"), Decimal("1.25")):
            with self.assertRaises(ValueError):
                client.place_trailing_stop(symbol="BTCUSDT", side="SELL", quantity=Decimal("0.01"), callback_rate=bad, filters=FILTERS, mark_price=MARK)
        self.assertEqual(client.calls, [])


class CancelTests(unittest.TestCase):
    def test_cancel_dry_run_and_live_delete(self) -> None:
        client = RecordingTradingClient(make_config(), {"/fapi/v1/order": (200, json.dumps({"orderId": 5, "status": "CANCELED"}))})
        dry = client.cancel_order(symbol="btcusdt", order_id=5)
        self.assertEqual(dry.status, "dry_run")
        self.assertEqual(dry.request["params"]["orderId"], 5)
        self.assertEqual(client.calls, [])
        with self.assertRaises(ValueError):
            client.cancel_order(symbol="BTCUSDT")
        live = client.cancel_order(symbol="BTCUSDT", client_order_id="kh-abc", dry_run=False)
        self.assertEqual(live.status, "submitted")
        self.assertEqual(client.paths(), ["DELETE /fapi/v1/order"])
        self.assertEqual(client.calls[0]["query"]["origClientOrderId"], ["kh-abc"])

    def test_cancel_live_respects_allowlist_and_credentials(self) -> None:
        client = RecordingTradingClient(make_config(api_key="", api_secret="", live_symbols=("ETHUSDT",)))
        with self.assertRaises(RuntimeError) as ctx:
            client.cancel_order(symbol="BTCUSDT", order_id=1, dry_run=False)
        self.assertIn("BINANCE_LIVE_SYMBOLS", str(ctx.exception))
        client2 = RecordingTradingClient(make_config(api_key="", api_secret=""))
        with self.assertRaises(RuntimeError):
            client2.cancel_order(symbol="BTCUSDT", order_id=1, dry_run=False)
        self.assertEqual(client2.calls, [])


if __name__ == "__main__":
    unittest.main()
