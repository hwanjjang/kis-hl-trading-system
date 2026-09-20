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
        self.assertEqual(params["triggerPrice"], "74000.10")  # SELL stop rounds up: triggers earlier
        self.assertEqual(params["workingType"], "MARK_PRICE")
        self.assertNotIn("quantity", params)
        self.assertNotIn("reduceOnly", params)

    def test_reduce_only_stop_requires_quantity_and_rounds(self) -> None:
        client = RecordingTradingClient(make_config(), {"/fapi/v1/ticker/price": (200, json.dumps({"symbol": "BTCUSDT", "price": "76000.00"}))})
        with self.assertRaises(ValueError):
            client.place_stop_market(symbol="BTCUSDT", side="SELL", stop_price=Decimal("74000"), close_position=False, filters=FILTERS, mark_price=MARK)
        submission = client.place_stop_market(
            symbol="BTCUSDT", side="BUY", stop_price=Decimal("78000.01"), close_position=False, quantity=Decimal("0.0104"),
            working_type="CONTRACT_PRICE", filters=FILTERS, mark_price=MARK,
        )
        params = submission.request["params"]
        self.assertEqual(params["reduceOnly"], "true")
        self.assertEqual(params["quantity"], "0.010")
        self.assertEqual(params["triggerPrice"], "78000.00")  # BUY stop rounds down: triggers earlier
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
        self.assertEqual(params["activatePrice"], "77000.10")
        self.assertEqual(params["quantity"], "0.010")
        self.assertEqual(params["reduceOnly"], "true")
        self.assertEqual(params["workingType"], "MARK_PRICE")
        no_activation = client.place_trailing_stop(symbol="BTCUSDT", side="SELL", quantity=Decimal("0.01"), callback_rate=Decimal("2"), filters=FILTERS, mark_price=MARK)
        self.assertNotIn("activatePrice", no_activation.request["params"])
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


ALGO_ACK = json.dumps({"algoId": 2146760, "clientAlgoId": "kh-algo", "algoType": "CONDITIONAL", "orderType": "STOP_MARKET", "algoStatus": "NEW", "symbol": "BTCUSDT"})
LAST_PRICE = json.dumps({"symbol": "BTCUSDT", "price": "76010.00"})


class AlgoOrderRoutingTests(unittest.TestCase):
    """Conditional orders moved to the Algo Order API on 2025-12-09; /fapi/v1/order returns -4120."""

    def test_stop_market_targets_algo_order_endpoint_with_algo_params(self) -> None:
        client = RecordingTradingClient(make_config())
        submission = client.place_stop_market(symbol="BTCUSDT", side="SELL", stop_price=Decimal("74000"), filters=FILTERS, mark_price=MARK)
        self.assertEqual(submission.request["path"], "/fapi/v1/algoOrder")
        params = submission.request["params"]
        self.assertEqual(params["algoType"], "CONDITIONAL")
        self.assertEqual(params["type"], "STOP_MARKET")
        self.assertEqual(params["triggerPrice"], "74000.00")
        self.assertNotIn("stopPrice", params)
        self.assertNotIn("newClientOrderId", params)
        self.assertRegex(params["clientAlgoId"], r"^[A-Za-z0-9._:/-]{1,36}$")
        self.assertEqual(params["closePosition"], "true")

    def test_trailing_stop_targets_algo_order_endpoint_with_activate_price(self) -> None:
        client = RecordingTradingClient(make_config())
        submission = client.place_trailing_stop(
            symbol="BTCUSDT", side="SELL", quantity=Decimal("0.01"), callback_rate=Decimal("1.5"),
            activation_price=Decimal("77000"), filters=FILTERS, mark_price=MARK,
        )
        self.assertEqual(submission.request["path"], "/fapi/v1/algoOrder")
        params = submission.request["params"]
        self.assertEqual(params["algoType"], "CONDITIONAL")
        self.assertEqual(params["activatePrice"], "77000.00")
        self.assertNotIn("activationPrice", params)
        self.assertIn("clientAlgoId", params)

    def test_live_stop_posts_to_algo_order_and_extracts_algo_id(self) -> None:
        client = RecordingTradingClient(make_config(), {"/fapi/v1/positionSide/dual": (200, ONE_WAY), "/fapi/v1/algoOrder": (200, ALGO_ACK)})
        submission = client.place_stop_market(symbol="BTCUSDT", side="SELL", stop_price=Decimal("74000"), filters=FILTERS, mark_price=MARK, dry_run=False)
        self.assertEqual(submission.status, "submitted")
        self.assertEqual(client.paths(), ["GET /fapi/v1/positionSide/dual", "POST /fapi/v1/algoOrder"])
        self.assertEqual(extract_binance_order_id(submission.response), "2146760")

    def test_exchange_test_is_unavailable_for_algo_orders(self) -> None:
        client = RecordingTradingClient(make_config())
        with self.assertRaises(ValueError):
            client.place_stop_market(symbol="BTCUSDT", side="SELL", stop_price=Decimal("74000"), filters=FILTERS, mark_price=MARK, exchange_test=True)
        self.assertEqual(client.calls, [])

    def test_cancel_algo_order_uses_algo_endpoint(self) -> None:
        client = RecordingTradingClient(make_config())

        def send(method, url, headers, body):
            path = urlsplit(url).path
            client.calls.append({"method": method, "path": path, "query": parse_qs(urlsplit(url).query), "headers": headers})
            if method == "GET":
                return 200, {}, json.dumps({"algoId": 7, "clientAlgoId": "kh-algo", "symbol": "BTCUSDT", "algoStatus": "NEW"})
            return 200, {}, json.dumps({"algoId": 7, "clientAlgoId": "kh-algo", "code": "200", "msg": "success"})
        client.send = send  # type: ignore[method-assign]
        dry = client.cancel_algo_order(symbol="BTCUSDT", algo_id=7)
        self.assertEqual(dry.status, "dry_run")
        self.assertEqual(dry.request["path"], "/fapi/v1/algoOrder")
        self.assertEqual(dry.request["params"]["algoId"], 7)
        self.assertEqual(client.calls, [])
        live = client.cancel_algo_order(symbol="BTCUSDT", client_algo_id="kh-algo", dry_run=False)
        self.assertEqual(live.status, "submitted")
        self.assertEqual(client.paths(), ["GET /fapi/v1/algoOrder", "DELETE /fapi/v1/algoOrder"])
        self.assertEqual(client.calls[1]["query"]["clientAlgoId"], ["kh-algo"])
        with self.assertRaises(ValueError):
            client.cancel_algo_order(symbol="BTCUSDT")

    def test_open_algo_orders_uses_open_algo_orders_path_with_optional_symbol(self) -> None:
        # Verified 2026-09-19: an unauthenticated GET to /fapi/v1/openAlgoOrders answers 401 -2014
        # (route exists) while /fapi/v1/algoOpenOrders answers 404.
        client = RecordingTradingClient(make_config(), {"/fapi/v1/openAlgoOrders": (200, json.dumps([{"algoId": 1}]))})
        self.assertEqual(client.open_algo_orders("btcusdt"), [{"algoId": 1}])
        self.assertEqual(client.calls[0]["path"], "/fapi/v1/openAlgoOrders")
        self.assertEqual(client.calls[0]["query"]["symbol"], ["BTCUSDT"])
        self.assertEqual(client.open_algo_orders(), [{"algoId": 1}])
        self.assertNotIn("symbol", client.calls[1]["query"])


class UnknownOutcomeTests(unittest.TestCase):
    def test_5xx_unknown_error_reconciles_by_client_order_id(self) -> None:
        found = json.dumps({"orderId": 99, "clientOrderId": "kh-x", "status": "NEW"})
        client = RecordingTradingClient(
            make_config(),
            {"/fapi/v1/positionSide/dual": (200, ONE_WAY), "/fapi/v1/order": (503, json.dumps({"code": -1000, "msg": "Unknown error, please check your request or try again later."}))},
        )
        # The GET reconciliation shares the path; answer it by method.
        original = client.send
        def send(method, url, headers, body):
            if method == "GET" and urlsplit(url).path == "/fapi/v1/order":
                client.calls.append({"method": method, "path": "/fapi/v1/order", "query": parse_qs(urlsplit(url).query), "headers": headers})
                return 200, {}, found
            return original(method, url, headers, body)
        client.send = send  # type: ignore[method-assign]
        submission = client.place_order(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0.01"), filters=FILTERS, mark_price=MARK, client_order_id="kh-x", dry_run=False)
        self.assertEqual(submission.status, "submitted")
        self.assertEqual(submission.response["orderId"], 99)
        self.assertEqual(submission.request["outcome"], "reconciled_after_unknown")
        self.assertEqual(client.paths()[-2:], ["POST /fapi/v1/order", "GET /fapi/v1/order"])
        self.assertEqual(client.calls[-1]["query"]["origClientOrderId"], ["kh-x"])

    def test_5xx_without_reconciliation_stays_unknown_not_rejected(self) -> None:
        client = RecordingTradingClient(
            make_config(),
            {"/fapi/v1/positionSide/dual": (200, ONE_WAY), "/fapi/v1/order": (503, json.dumps({"code": -1000, "msg": "Unknown error"}))},
        )
        submission = client.place_order(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0.01"), filters=FILTERS, mark_price=MARK, dry_run=False)
        self.assertEqual(submission.status, "unknown")
        self.assertIn("error", submission.response)

    def test_transport_exception_during_signed_send_is_unknown(self) -> None:
        client = RecordingTradingClient(make_config(), {"/fapi/v1/positionSide/dual": (200, ONE_WAY)})
        original = client.send
        def send(method, url, headers, body):
            if method == "POST":
                raise TimeoutError("timed out")
            if method == "GET" and urlsplit(url).path == "/fapi/v1/order":
                raise TimeoutError("timed out again")
            return original(method, url, headers, body)
        client.send = send  # type: ignore[method-assign]
        submission = client.place_order(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0.01"), filters=FILTERS, mark_price=MARK, dry_run=False)
        self.assertEqual(submission.status, "unknown")

    def test_4xx_is_still_rejected(self) -> None:
        client = RecordingTradingClient(
            make_config(),
            {"/fapi/v1/positionSide/dual": (200, ONE_WAY), "/fapi/v1/order": (400, json.dumps({"code": -2019, "msg": "Margin is insufficient."}))},
        )
        submission = client.place_order(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0.01"), filters=FILTERS, mark_price=MARK, dry_run=False)
        self.assertEqual(submission.status, "rejected")


class NotionalAndDirectionTests(unittest.TestCase):
    def test_reduce_only_entries_skip_min_notional(self) -> None:
        client = RecordingTradingClient(make_config())
        submission = client.place_order(symbol="BTCUSDT", side="SELL", order_type="MARKET", quantity=Decimal("0.001"), reduce_only=True, filters=FILTERS, mark_price=Decimal("49000"))
        self.assertEqual(submission.status, "dry_run")
        with self.assertRaises(ValueError):
            client.place_order(symbol="BTCUSDT", side="SELL", order_type="MARKET", quantity=Decimal("0.001"), filters=FILTERS, mark_price=Decimal("49000"))

    def test_contract_price_stops_use_last_price_for_direction(self) -> None:
        client = RecordingTradingClient(make_config(), {"/fapi/v1/ticker/price": (200, LAST_PRICE)})
        # mark 76000, last 76010: a SELL stop at 76005 is valid against last price only.
        submission = client.place_stop_market(symbol="BTCUSDT", side="SELL", stop_price=Decimal("76005"), working_type="CONTRACT_PRICE", filters=FILTERS, mark_price=MARK)
        self.assertEqual(submission.status, "dry_run")
        self.assertEqual(client.paths(), ["GET /fapi/v1/ticker/price"])
        with self.assertRaises(ValueError):
            client.place_stop_market(symbol="BTCUSDT", side="SELL", stop_price=Decimal("76005"), working_type="MARK_PRICE", filters=FILTERS, mark_price=MARK)

    def test_trailing_activation_direction_is_validated(self) -> None:
        client = RecordingTradingClient(make_config())
        with self.assertRaises(ValueError):
            client.place_trailing_stop(symbol="BTCUSDT", side="SELL", quantity=Decimal("0.01"), callback_rate=Decimal("1"), activation_price=Decimal("75000"), filters=FILTERS, mark_price=MARK)
        with self.assertRaises(ValueError):
            client.place_trailing_stop(symbol="BTCUSDT", side="BUY", quantity=Decimal("0.01"), callback_rate=Decimal("1"), activation_price=Decimal("77000"), filters=FILTERS, mark_price=MARK)
        ok = client.place_trailing_stop(symbol="BTCUSDT", side="BUY", quantity=Decimal("0.01"), callback_rate=Decimal("1"), activation_price=Decimal("75000"), filters=FILTERS, mark_price=MARK)
        self.assertEqual(ok.request["params"]["activatePrice"], "75000.00")


class UnknownOutcomeCodeTests(unittest.TestCase):
    def _client_with_order_error(self, status: int, body: str) -> RecordingTradingClient:
        return RecordingTradingClient(make_config(), {"/fapi/v1/positionSide/dual": (200, ONE_WAY), "/fapi/v1/order": (status, body)})

    def test_http_408_and_code_1007_are_unknown_not_rejected(self) -> None:
        for status, body in (
            (408, json.dumps({"code": -1007, "msg": "Timeout waiting for response from backend server. Send status unknown; execution status unknown."})),
            (400, json.dumps({"code": -1007, "msg": "execution status unknown"})),
            (400, json.dumps({"code": -1007, "msg": "Timeout waiting for response from backend server."})),
        ):
            client = self._client_with_order_error(status, body)
            submission = client.place_order(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0.01"), filters=FILTERS, mark_price=MARK, dry_run=False)
            self.assertEqual(submission.status, "unknown", body)


class CancelAlgoSymbolGuardTests(unittest.TestCase):
    def test_live_cancel_algo_verifies_the_order_symbol_before_deleting(self) -> None:
        client = RecordingTradingClient(make_config(live_symbols=("BTCUSDT",)))
        original = client.send

        def send(method, url, headers, body):
            path = urlsplit(url).path
            client.calls.append({"method": method, "path": path, "query": parse_qs(urlsplit(url).query), "headers": headers})
            if method == "GET" and path == "/fapi/v1/algoOrder":
                return 200, {}, json.dumps({"algoId": 7, "symbol": "ETHUSDT", "algoStatus": "NEW"})
            return 200, {}, "{}"
        client.send = send  # type: ignore[method-assign]
        with self.assertRaises(RuntimeError) as ctx:
            client.cancel_algo_order(symbol="BTCUSDT", algo_id=7, dry_run=False)
        self.assertIn("ETHUSDT", str(ctx.exception))
        self.assertEqual(client.paths(), ["GET /fapi/v1/algoOrder"])

    def test_live_cancel_algo_fails_closed_when_lookup_fails(self) -> None:
        client = RecordingTradingClient(make_config(), {"/fapi/v1/algoOrder": (400, json.dumps({"code": -2013, "msg": "Order does not exist."}))})
        with self.assertRaises(RuntimeError):
            client.cancel_algo_order(symbol="BTCUSDT", algo_id=7, dry_run=False)
        self.assertEqual([c["method"] for c in client.calls], ["GET"])

    def test_live_cancel_algo_deletes_when_symbol_matches(self) -> None:
        client = RecordingTradingClient(make_config())
        original = client.send

        def send(method, url, headers, body):
            path = urlsplit(url).path
            client.calls.append({"method": method, "path": path, "query": parse_qs(urlsplit(url).query), "headers": headers})
            if method == "GET":
                return 200, {}, json.dumps({"algoId": 7, "clientAlgoId": "kh-algo", "symbol": "BTCUSDT", "algoStatus": "NEW"})
            return 200, {}, json.dumps({"algoId": 7, "clientAlgoId": "kh-algo", "code": "200", "msg": "success"})
        client.send = send  # type: ignore[method-assign]
        submission = client.cancel_algo_order(symbol="btcusdt", client_algo_id="kh-algo", dry_run=False)
        self.assertEqual(submission.status, "submitted")
        self.assertEqual(client.paths(), ["GET /fapi/v1/algoOrder", "DELETE /fapi/v1/algoOrder"])
        self.assertEqual(client.calls[0]["query"]["clientAlgoId"], ["kh-algo"])


class ReconciledStatusTests(unittest.TestCase):
    def _client(self, lookup_body: str, path: str) -> RecordingTradingClient:
        client = RecordingTradingClient(make_config(), {"/fapi/v1/positionSide/dual": (200, ONE_WAY)})

        def send(method, url, headers, body):
            p = urlsplit(url).path
            client.calls.append({"method": method, "path": p, "query": parse_qs(urlsplit(url).query), "headers": headers})
            if method == "GET" and p == "/fapi/v1/positionSide/dual":
                return 200, {}, ONE_WAY
            if method == "POST":
                return 503, {}, json.dumps({"code": -1000, "msg": "Unknown error"})
            return 200, {}, lookup_body
        client.send = send  # type: ignore[method-assign]
        return client

    def test_reconciled_terminal_algo_status_is_rejected_not_submitted(self) -> None:
        for status in ("REJECTED", "CANCELED", "EXPIRED"):
            client = self._client(json.dumps({"algoId": 5, "clientAlgoId": "x", "symbol": "BTCUSDT", "algoStatus": status}), "/fapi/v1/algoOrder")
            submission = client.place_stop_market(symbol="BTCUSDT", side="SELL", stop_price=Decimal("74000"), filters=FILTERS, mark_price=MARK, dry_run=False)
            self.assertEqual(submission.status, "rejected", status)
            self.assertEqual(submission.request["outcome"], "reconciled_terminal")
            self.assertEqual(submission.response["algoStatus"], status)

    def test_reconciled_live_algo_status_is_submitted(self) -> None:
        for status in ("NEW", "TRIGGERING", "TRIGGERED"):
            client = self._client(json.dumps({"algoId": 5, "clientAlgoId": "x", "symbol": "BTCUSDT", "algoStatus": status}), "/fapi/v1/algoOrder")
            submission = client.place_stop_market(symbol="BTCUSDT", side="SELL", stop_price=Decimal("74000"), filters=FILTERS, mark_price=MARK, dry_run=False)
            self.assertEqual(submission.status, "submitted", status)

    def test_reconciled_terminal_regular_status_is_rejected(self) -> None:
        client = self._client(json.dumps({"orderId": 9, "clientOrderId": "x", "status": "EXPIRED"}), "/fapi/v1/order")
        submission = client.place_order(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0.01"), filters=FILTERS, mark_price=MARK, dry_run=False)
        self.assertEqual(submission.status, "rejected")
        client2 = self._client(json.dumps({"orderId": 9, "clientOrderId": "x", "status": "FILLED"}), "/fapi/v1/order")
        submission2 = client2.place_order(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0.01"), filters=FILTERS, mark_price=MARK, dry_run=False)
        self.assertEqual(submission2.status, "submitted")


class ReconciledPartialFillTests(unittest.TestCase):
    def test_expired_ioc_with_executed_quantity_is_not_rejected(self) -> None:
        client = RecordingTradingClient(make_config(), {"/fapi/v1/positionSide/dual": (200, ONE_WAY)})

        def send(method, url, headers, body):
            p = urlsplit(url).path
            client.calls.append({"method": method, "path": p, "query": parse_qs(urlsplit(url).query), "headers": headers})
            if method == "GET" and p == "/fapi/v1/positionSide/dual":
                return 200, {}, ONE_WAY
            if method == "POST":
                return 503, {}, json.dumps({"code": -1000, "msg": "Unknown error"})
            return 200, {}, json.dumps({"orderId": 9, "clientOrderId": "x", "status": "EXPIRED", "origQty": "0.010", "executedQty": "0.004"})
        client.send = send  # type: ignore[method-assign]
        submission = client.place_order(symbol="BTCUSDT", side="BUY", order_type="LIMIT", quantity=Decimal("0.01"), price=Decimal("75000"), tif="IOC", filters=FILTERS, dry_run=False)
        self.assertEqual(submission.status, "submitted")
        self.assertEqual(submission.request["outcome"], "reconciled_partial_fill")
        self.assertEqual(submission.response["executedQty"], "0.004")


class CancelReconciliationTests(unittest.TestCase):
    def _client(self, lookup_body: str, lookup_status: int = 200) -> RecordingTradingClient:
        client = RecordingTradingClient(make_config())

        def send(method, url, headers, body):
            p = urlsplit(url).path
            client.calls.append({"method": method, "path": p, "query": parse_qs(urlsplit(url).query), "headers": headers})
            if method == "DELETE":
                return 503, {}, json.dumps({"code": -1000, "msg": "Unknown error"})
            if method == "GET" and p == "/fapi/v1/algoOrder" and not client.calls[:-1]:
                # first GET is the pre-cancel symbol check
                return 200, {}, json.dumps({"algoId": 7, "clientAlgoId": "kh-algo", "symbol": "BTCUSDT", "algoStatus": "NEW"})
            return lookup_status, {}, lookup_body
        client.send = send  # type: ignore[method-assign]
        return client

    def test_algo_cancel_unknown_is_confirmed_by_lookup(self) -> None:
        client = self._client(json.dumps({"algoId": 7, "clientAlgoId": "kh-algo", "symbol": "BTCUSDT", "algoStatus": "CANCELED"}))
        submission = client.cancel_algo_order(symbol="BTCUSDT", algo_id=7, dry_run=False)
        self.assertEqual(submission.status, "submitted")
        self.assertEqual(submission.request["outcome"], "reconciled_cancel")
        self.assertEqual(client.paths(), ["GET /fapi/v1/algoOrder", "DELETE /fapi/v1/algoOrder", "GET /fapi/v1/algoOrder"])
        self.assertEqual(client.calls[-1]["query"]["algoId"], ["7"])

    def test_algo_cancel_unknown_stays_unknown_when_order_still_live(self) -> None:
        client = self._client(json.dumps({"algoId": 7, "clientAlgoId": "kh-algo", "symbol": "BTCUSDT", "algoStatus": "NEW"}))
        submission = client.cancel_algo_order(symbol="BTCUSDT", algo_id=7, dry_run=False)
        self.assertEqual(submission.status, "unknown")

    def test_regular_cancel_unknown_is_confirmed_by_order_id_lookup(self) -> None:
        client = RecordingTradingClient(make_config())

        def send(method, url, headers, body):
            p = urlsplit(url).path
            client.calls.append({"method": method, "path": p, "query": parse_qs(urlsplit(url).query), "headers": headers})
            if method == "DELETE":
                return 503, {}, json.dumps({"code": -1000, "msg": "Unknown error"})
            return 200, {}, json.dumps({"orderId": 5, "clientOrderId": "c", "status": "CANCELED", "executedQty": "0"})
        client.send = send  # type: ignore[method-assign]
        submission = client.cancel_order(symbol="BTCUSDT", order_id=5, dry_run=False)
        self.assertEqual(submission.status, "submitted")
        self.assertEqual(submission.request["outcome"], "reconciled_cancel")
        self.assertEqual(client.calls[-1]["query"]["orderId"], ["5"])
