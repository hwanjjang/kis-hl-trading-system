"""Native trailing contract and lifecycle tests; no network or real credentials."""
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from kis_hl.config import HyperliquidConfig
from kis_hl.hyperliquid.client import HyperliquidTradingClient
from kis_hl.instruments import capabilities
from kis_hl.managed_execution import ExecutionStore, Supervisor, validate_plan
from tests.test_managed_execution import Gateway, plan


class NativeTrailingClientTests(unittest.TestCase):
    def client(self):
        c = HyperliquidTradingClient(HyperliquidConfig(
            base_url="https://api.hyperliquid-testnet.xyz", account_address="fixture",
            private_key="fixture", key_profile="default"))
        info = Mock()
        info.name_to_asset.return_value = 0
        info.asset_to_sz_decimals = {0: 2}
        info.user_state.return_value = {"assetPositions": [{"position": {"coin": "BTC", "szi": "1"}}]}
        exchange = Mock()
        c._sdk = info, exchange
        public = patch("kis_hl.hyperliquid.client.HyperliquidInfoClient")
        public_client = public.start().return_value
        public_client.clearinghouse_state.return_value = info.user_state.return_value
        self.addCleanup(public.stop)
        return c, info, exchange

    def test_dry_run_requires_no_sdk_credentials_or_network(self):
        c, _, _ = self.client()
        c._load_sdk = Mock(side_effect=AssertionError("SDK must not load"))
        result = c.place_trailing_stop_order(symbol="BTC", side="sell", size=Decimal("1"), retracement=Decimal("4"))
        self.assertTrue(result.dry_run)
        self.assertEqual(result.request["retracement"], {"px": "4"})
        self.assertTrue(result.request["reduce_only"])

    def test_invalid_parameters_never_send(self):
        c, _, _ = self.client()
        for changes in ({"size": Decimal("NaN")}, {"retracement": Decimal("Infinity")},
                        {"retracement": Decimal("0")}, {"retracement_unit": "bogus"},
                        {"retracement_unit": "percent", "retracement": Decimal("100")},
                        {"retracement_unit": "percent", "retracement": Decimal("0.00001")},
                        {"activation_price": Decimal("NaN")}, {"symbol": "BTCUSDC"},
                        {"side": "invalid"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                c.place_trailing_stop_order(**(dict(symbol="BTC", side="sell", size=Decimal("1"), retracement=Decimal("4")) | changes))

    @patch("kis_hl.hyperliquid.client.send_trailing_action")
    def test_wire_contract_and_opaque_ack_stays_unknown(self, send):
        c, info, _ = self.client()
        send.return_value = {"status": "ok", "response": {"type": "default"}}
        result = c.place_trailing_stop_order(symbol="BTC", side="sell", size=Decimal("1"),
            retracement=Decimal("5"), retracement_unit="percent", dry_run=False)
        self.assertEqual(result.status, "unknown")
        action = send.call_args.args[1]
        self.assertEqual(action, {"type": "trailingStop", "asset": 0, "isBuy": False,
            "sz": "1", "reduceOnly": True, "retracement": {"pct": "5.0000%"}, "activationPx": None})
        self.assertEqual(list(action), ["type", "asset", "isBuy", "sz", "reduceOnly", "retracement", "activationPx"])
        self.assertNotIn("cloid", action)
        info.name_to_asset.assert_called_once_with("BTC")
        info.user_state.assert_not_called()

    @patch("kis_hl.hyperliquid.client.send_trailing_action")
    def test_live_guards_lot_side_and_allowlist(self, send):
        c, _, _ = self.client()
        for changes in ({"size": Decimal("1.001")}, {"side": "buy"}, {"symbol": "SOL"},
                        {"symbol": "xyz:SP500"}):
            with self.subTest(changes=changes), self.assertRaises((ValueError, RuntimeError)):
                c.place_trailing_stop_order(**(dict(symbol="BTC", side="sell", size=Decimal("1"), retracement=Decimal("4"), dry_run=False) | changes))
        send.assert_not_called()

    @patch("kis_hl.hyperliquid.client.send_trailing_action")
    def test_response_rejection_and_native_id(self, send):
        c, _, _ = self.client()
        for response, expected in [({"status": "err", "response": "bad request"}, "rejected"),
            ({"status": "ok", "response": {"type": "order", "data": {"statuses": [{"resting": {"oid": 42}}]}}}, "submitted"),
            ({"status": "ok", "response": {"data": {"statuses": [{"error": "rejected"}]}}}, "rejected")]:
            send.return_value = response
            self.assertEqual(c.place_trailing_stop_order(symbol="BTC", side="sell", size=Decimal("1"), retracement=Decimal("4"), dry_run=False).status, expected)


class NativeTrailingManagedTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.store = ExecutionStore(Path(tmp.name)/"state.sqlite")
        self.g = Gateway(); self.g.native_trailing = True
        preflight, snapshot = self.g.preflight, self.g.snapshot
        self.g.preflight = lambda *a: preflight(*a) | {"trailing_price_step": "0.01"}
        self.g.snapshot = lambda *a: snapshot(*a) | {"trailing_price_step": "0.01"}
        self.worker = Supervisor(self.store, self.g, live=True)

    def start(self):
        row = self.store.enqueue("scope", plan(trailing_provider="native"), live=True, now_ms=1)
        self.worker.step(row["id"], 2)
        self.g.size = self.g.filled = "1"
        self.g.orders[self.g.sent[0]["id"]]["status"] = "filled"
        self.worker.step(row["id"], 3)  # fixed SL
        self.worker.step(row["id"], 4)  # native trailing
        return row

    def test_independent_frozen_distances_preserve_fixed_stop_after_restart(self):
        p = plan(trailing_provider="native", local_atr_multiple="1.5", native_atr_multiple="3")
        row = self.store.enqueue("scope", p, live=True, now_ms=1)
        self.worker.step(row["id"], 2)
        self.g.size = self.g.filled = "1"
        self.g.orders[self.g.sent[0]["id"]]["status"] = "filled"
        self.worker.step(row["id"], 3)
        self.worker.step(row["id"], 4)
        saved = self.store.get(row["id"])
        self.assertEqual(saved["trail"]["distance"], "3.0")
        self.assertEqual(self.g.sent[1]["trigger_price"], "96")
        self.assertEqual(Decimal(self.g.sent[2]["retracement"]), Decimal("6"))
        self.g.orders[self.g.sent[2]["id"]].update(active=True, retracement="6", retracement_unit="quote")
        self.worker = Supervisor(self.store, self.g, live=True)
        result = self.worker.step(row["id"], 5)
        self.assertEqual(result["state"], "PROTECTED")
        self.assertEqual(result["trail"]["distance"], "3.0")
        self.assertEqual(len(self.g.sent), 3)

    def condition_error(self):
        row = self.start()
        order = self.g.orders[self.g.sent[-1]["id"]]
        order["trailing_readback_error"] = "Unverified native trailing condition format"
        return row, order

    def test_condition_error_retains_sl_without_retry_or_timeout_exit(self):
        row, _ = self.condition_error()
        for now in (5, 6000, 7000):
            result = Supervisor(self.store, self.g, live=True).step(row["id"], now)
            self.assertEqual(result["state"], "INTERVENTION")
            self.assertTrue(result["native_trailing_intervention"])
            self.assertEqual(result["covered_size"], "1")
            self.assertEqual(result["trailing_covered_size"], "0")
            self.assertIsNone(result["exit_requested_ms"])
        self.assertEqual([a["kind"] for a in self.g.sent], ["entry", "stop", "trailing"])

    def test_condition_error_still_exits_on_fixed_sl_loss(self):
        row, _ = self.condition_error()
        self.worker.step(row["id"], 5)
        self.g.orders[self.g.sent[1]["id"]]["status"] = "canceled"
        self.worker.step(row["id"], 6000)
        self.assertEqual(self.g.sent[-1]["kind"], "exit")

    def test_condition_error_does_not_block_explicit_exit(self):
        row, _ = self.condition_error()
        self.worker.step(row["id"], 5)
        self.store.request_exit(row["id"], 6)
        self.worker.step(row["id"], 7)
        self.assertEqual(self.g.sent[-1]["kind"], "exit")

    def test_condition_error_recovers_on_valid_same_id_readback(self):
        row, order = self.condition_error()
        self.worker.step(row["id"], 5)
        order.pop("trailing_readback_error")
        order.update(active=False, retracement="4", retracement_unit="quote")
        result = self.worker.step(row["id"], 6000)
        self.assertEqual(result["state"], "PROTECTING")
        self.assertFalse(result.get("native_trailing_intervention"))
        order.update(active=True, trigger_price="100")
        self.assertEqual(self.worker.step(row["id"], 6001)["state"], "PROTECTED")
        self.assertEqual(len(self.g.sent), 3)

    def test_terminal_condition_error_exits_and_flat_cleanup_still_completes(self):
        row, order = self.condition_error()
        self.worker.step(row["id"], 5)
        order["status"] = "canceled"
        self.worker.step(row["id"], 6)
        self.assertEqual(self.g.sent[-1]["kind"], "exit")
        self.g.orders[self.g.sent[-1]["id"]]["status"] = "filled"
        self.g.size = "0"
        self.assertEqual(self.worker.step(row["id"], 7)["state"], "CLEANUP")
        self.assertEqual(self.worker.step(row["id"], 8)["state"], "CLOSED")

    def test_condition_error_does_not_override_foreign_account_intervention(self):
        row, _ = self.condition_error()
        self.worker.step(row["id"], 5)
        self.g.foreign = True
        result = self.worker.step(row["id"], 6)
        self.assertFalse(result.get("native_trailing_intervention"))
        self.g.foreign = False
        self.g.orders[self.g.sent[1]["id"]]["status"] = "canceled"
        self.assertEqual(self.worker.step(row["id"], 6000)["state"], "INTERVENTION")
        self.assertEqual(len(self.g.sent), 3)

    def test_transport_failure_preserves_condition_intervention_sl_supervision(self):
        row, _ = self.condition_error()
        self.worker.step(row["id"], 5)
        with patch.object(self.g, "snapshot", side_effect=RuntimeError("offline")):
            result = self.worker.step(row["id"], 6)
        self.assertTrue(result.get("native_trailing_intervention"))
        self.g.orders[self.g.sent[1]["id"]]["status"] = "canceled"
        self.worker.step(row["id"], 6000)
        self.assertEqual(self.g.sent[-1]["kind"], "exit")

    def test_exit_deadline_clears_native_exception_and_keeps_generic_freeze(self):
        row = self.reject_trailing()
        self.worker.step(row["id"], 5)
        self.store.request_exit(row["id"], 6)
        result = self.worker.step(row["id"], 60007)
        self.assertEqual(result["state"], "INTERVENTION")
        self.assertFalse(result.get("native_trailing_intervention"))
        result = self.worker.step(row["id"], 60008)
        self.assertIn("budget exhausted", result["reason"])
        self.assertEqual(len(self.g.sent), 3)

    def test_native_policy_is_explicit_and_venue_limited(self):
        self.assertEqual(validate_plan(plan(), 1)["trailing_provider"], "local")
        for changes in ({"trailing_provider": "typo"}, {"trailing_provider": "native", "instrument": "kis:SPY", "verified_price_step": "0.01"}):
            p = plan(); p.update(changes)
            with self.assertRaises(ValueError): validate_plan(p, 1)
        self.assertEqual(capabilities("hl:BTC")["native_trailing"], "documented_requires_readback")
        self.assertEqual(capabilities("kis:SPY")["native_trailing"], "unverified")

    def test_partial_entry_gets_fixed_sl_before_native_trailing(self):
        row = self.store.enqueue("scope", plan(trailing_provider="native"), live=True, now_ms=1)
        self.worker.step(row["id"], 2)
        self.g.size = self.g.filled = "0.4"
        self.worker.step(row["id"], 3); self.worker.step(row["id"], 4)
        self.assertEqual([a["kind"] for a in self.g.sent], ["entry", "stop"])
        self.assertEqual(self.g.sent[-1]["quantity"], "0.4")
        self.g.orders[self.g.sent[0]["id"]]["status"] = "canceled"
        self.worker.step(row["id"], 5)
        self.assertEqual(self.g.sent[-1]["kind"], "trailing")
        self.assertEqual(self.g.sent[-1]["quantity"], "0.4")

    def test_unknown_trailing_never_retries_after_restart(self):
        original = self.g.submit
        def submit(row, a):
            if a["kind"] == "trailing":
                self.g.sent.append(dict(a)); raise TimeoutError()
            return original(row, a)
        self.g.submit = submit
        row = self.start()
        worker = Supervisor(self.store, self.g, live=True)
        for t in (5, 6000, 7000): worker.step(row["id"], t)
        self.assertEqual(len([a for a in self.g.sent if a["kind"] == "trailing"]), 1)
        self.assertEqual(self.store.get(row["id"])["state"], "INTERVENTION")
        self.assertEqual(self.g.orders[self.g.sent[1]["id"]]["status"], "open")

    def reject_trailing(self):
        original = self.g.submit
        def submit(row, a):
            if a["kind"] == "trailing":
                self.g.sent.append(dict(a))
                return {"status": "rejected", "order_id": None}
            return original(row, a)
        self.g.submit = submit
        row = self.start()
        return row

    def test_rejection_retains_fixed_stop_without_exit_or_retry_after_restart(self):
        row = self.reject_trailing()
        for now in (5, 6000, 7000):
            result = Supervisor(self.store, self.g, live=True).step(row["id"], now)
            self.assertEqual(result["state"], "INTERVENTION")
            self.assertIsNone(result["exit_requested_ms"])
            self.assertEqual(result["covered_size"], "1")
        self.assertEqual([a["kind"] for a in self.g.sent], ["entry", "stop", "trailing"])
        self.assertEqual(self.g.orders[self.g.sent[1]["id"]]["status"], "open")

    def test_fixed_stop_loss_after_rejection_still_exits(self):
        row = self.reject_trailing()
        self.worker.step(row["id"], 5)
        self.g.orders[self.g.sent[1]["id"]]["status"] = "canceled"
        self.worker.step(row["id"], 6000)
        self.assertEqual(self.g.sent[-1]["kind"], "exit")

    def test_explicit_exit_after_rejection_is_not_blocked(self):
        row = self.reject_trailing()
        self.worker.step(row["id"], 5)
        self.store.request_exit(row["id"], 6)
        self.worker.step(row["id"], 7)
        self.assertEqual(self.g.sent[-1]["kind"], "exit")

    def test_rejected_trail_does_not_prevent_fixed_stop_cleanup_when_flat(self):
        row = self.reject_trailing()
        self.worker.step(row["id"], 5)
        self.g.size = "0"
        self.assertEqual(self.worker.step(row["id"], 6)["state"], "CLEANUP")
        self.assertEqual(self.worker.step(row["id"], 7)["state"], "CLOSED")

    def test_unrelated_reconciliation_failure_still_freezes_after_rejection(self):
        row = self.reject_trailing()
        self.worker.step(row["id"], 5)
        self.g.foreign = True
        self.worker.step(row["id"], 6)
        self.g.foreign = False
        self.g.orders[self.g.sent[1]["id"]]["status"] = "canceled"
        result = self.worker.step(row["id"], 6000)
        self.assertEqual(result["state"], "INTERVENTION")
        self.assertEqual([a["kind"] for a in self.g.sent], ["entry", "stop", "trailing"])

    def test_waiting_survives_grace_restart_and_becomes_active(self):
        row = self.start()
        order = self.g.orders[self.g.sent[-1]["id"]]
        order.update(active=False, retracement="4", retracement_unit="quote")
        for now in (5, 6000, 7000):
            result = Supervisor(self.store, self.g, live=True).step(row["id"], now)
            self.assertEqual(result["state"], "PROTECTING")
            self.assertEqual(result["trailing_covered_size"], "0")
            self.assertIsNone(result["exit_requested_ms"])
        order.update(active=True, best_price="104", trigger_price="100")
        self.assertEqual(self.worker.step(row["id"], 7001)["state"], "PROTECTED")
        self.assertEqual([a["kind"] for a in self.g.sent], ["entry", "stop", "trailing"])

    def test_waiting_does_not_mask_fixed_stop_loss(self):
        row = self.start()
        self.g.orders[self.g.sent[-1]["id"]].update(active=False, retracement="4", retracement_unit="quote")
        self.g.orders[self.g.sent[1]["id"]]["status"] = "canceled"
        self.worker.step(row["id"], 6000)
        self.assertEqual(self.g.sent[-1]["kind"], "exit")

    def test_distance_uses_own_precision_and_is_persisted_before_entry(self):
        p = plan(trailing_provider="native")
        p.update(limit_price="100000", max_notional="100001", max_portfolio_notional="1000000", max_correlated_notional="500000")
        preflight, snapshot = self.g.preflight, self.g.snapshot
        self.g.preflight = lambda *a: preflight(*a) | {"price": "100000", "ask": "100000.1", "price_step": "0.1", "trailing_price_step": "0.1", "available_notional": "1000000"}
        self.g.snapshot = lambda *a: snapshot(*a) | {"price": "100000", "entry_price": "100000", "price_step": "10", "trailing_price_step": "0.1"}
        observed_before_entry = []
        original = self.g.submit
        def submit(row, attempt):
            if attempt["kind"] == "entry":
                observed_before_entry.append(self.store.get(row["id"]).get("native_trailing_distance"))
            return original(row, attempt)
        self.g.submit = submit
        row = self.store.enqueue("scope", p, live=True, now_ms=1)
        self.worker.step(row["id"], 2)
        self.assertEqual(observed_before_entry, ["4"])
        self.g.size = self.g.filled = "1"
        self.g.orders[self.g.sent[0]["id"]]["status"] = "filled"
        self.worker.step(row["id"], 3)
        self.worker.step(row["id"], 4)
        self.assertEqual(self.g.sent[-1]["kind"], "trailing")
        self.assertEqual(Decimal(self.g.sent[-1]["retracement"]), Decimal("4"))

    def test_zero_normalized_distance_blocks_entry(self):
        p = plan(trailing_provider="native")
        p["atr"] = "0.001"
        original = self.g.preflight
        self.g.preflight = lambda *a: original(*a) | {"atr": "0.001", "trailing_price_step": "0.01"}
        row = self.store.enqueue("scope", p, live=True, now_ms=1)
        result = self.worker.step(row["id"], 2)
        self.assertEqual(result["state"], "INTERVENTION")
        self.assertEqual(self.g.sent, [])

    def test_old_inflight_row_normalizes_before_first_trail(self):
        row = self.store.enqueue("scope", plan(trailing_provider="native"), live=True, now_ms=1)
        current = self.worker.step(row["id"], 2)
        del current["native_trailing_distance"]
        self.store.save(current, 2)
        self.g.size = self.g.filled = "1"
        self.g.orders[self.g.sent[0]["id"]]["status"] = "filled"
        self.worker.step(row["id"], 3)
        self.worker.step(row["id"], 4)
        self.assertEqual(self.g.sent[-1]["kind"], "trailing")
        self.assertEqual(self.store.get(row["id"])["native_trailing_distance"], "4")

    def test_ack_is_not_coverage_and_active_readback_survives_restart(self):
        row = self.start()
        self.assertEqual(self.g.sent[-1]["kind"], "trailing")
        trailing = self.g.sent[-1]
        self.g.orders[trailing["id"]].update(active=True, retracement="4", retracement_unit="quote", best_price="104", trigger_price="100")
        result = self.worker.step(row["id"], 5)
        self.assertEqual(result["providers"]["trailing"], "native")
        self.assertEqual(result["trailing_covered_size"], "1")
        result = Supervisor(self.store, self.g, live=True).step(row["id"], 6)
        self.assertEqual(result["state"], "PROTECTED")
        self.assertEqual(len([a for a in self.g.sent if a["kind"] == "trailing"]), 1)

    def test_fractional_atr_rounds_distance_tighter_and_readback_uses_it(self):
        p = plan(trailing_provider="native")
        p["atr"] = "2.123456"
        original = self.g.preflight
        self.g.preflight = lambda *a: original(*a) | {"atr": p["atr"]}
        row = self.store.enqueue("scope", p, live=True, now_ms=1)
        self.worker.step(row["id"], 2)
        self.g.size = self.g.filled = "1"
        self.g.orders[self.g.sent[0]["id"]]["status"] = "filled"
        self.worker.step(row["id"], 3)
        self.worker.step(row["id"], 4)
        a = self.g.sent[-1]
        self.assertEqual(a["kind"], "trailing")
        self.assertEqual(Decimal(a["retracement"]), Decimal("4.24"))
        self.g.orders[a["id"]].update(active=True, retracement="4.24", retracement_unit="quote", best_price="105", trigger_price="100.76")
        self.assertEqual(self.worker.step(row["id"], 5)["trailing_covered_size"], "1")

    def test_canceled_native_trail_is_not_recreated_with_a_lower_watermark(self):
        row = self.start()
        self.g.orders[self.g.sent[-1]["id"]]["status"] = "canceled"
        self.worker.step(row["id"], 5)
        self.assertEqual(self.g.sent[-1]["kind"], "exit")
        self.assertEqual(len([a for a in self.g.sent if a["kind"] == "trailing"]), 1)

    def test_rejected_established_trail_exits_instead_of_resetting_watermark(self):
        row = self.start()
        order = self.g.orders[self.g.sent[-1]["id"]]
        order.update(active=True, retracement="4", retracement_unit="quote", best_price="104", trigger_price="100")
        self.assertEqual(self.worker.step(row["id"], 5)["state"], "PROTECTED")
        order["status"] = "rejected"
        self.worker.step(row["id"], 6)
        self.assertEqual(self.g.sent[-1]["kind"], "exit")
        self.assertEqual(len([a for a in self.g.sent if a["kind"] == "trailing"]), 1)

    def test_unverified_native_readback_does_not_claim_protection(self):
        row = self.start()
        result = self.worker.step(row["id"], 5)
        self.assertNotEqual(result["state"], "PROTECTED")
        self.assertEqual(result["trailing_covered_size"], "0")

    def test_flat_cleans_up_both_protections(self):
        row = self.start()
        self.g.size = "0"
        result = self.worker.step(row["id"], 5)
        self.assertEqual(result["state"], "CLEANUP")
        result = self.worker.step(row["id"], 6)
        self.assertEqual(result["state"], "CLOSED")


class NativeTrailingReadbackTests(unittest.TestCase):
    def test_directional_activation_rejects_immediate_value(self):
        from kis_hl.hyperliquid.trailing import parse_trailing_condition, trailing_readback
        order = {"orderType": "Trailing Stop Market", "isTrigger": True,
                 "reduceOnly": True, "side": "A"}
        for direction in ("above", "below"):
            condition = f"activation {direction} immediate, retracement 5, best 100"
            with self.subTest(direction=direction, check="parse"), self.assertRaises(ValueError):
                parse_trailing_condition(condition)
            with self.subTest(direction=direction, check="readback"), self.assertRaises(ValueError):
                trailing_readback(order | {"triggerCondition": condition}, retracement=Decimal("5"))

    def test_live_immediate_activation_clause_is_verified(self):
        from kis_hl.hyperliquid.trailing import trailing_readback
        order = {"orderType": "Trailing Stop Market", "isTrigger": True,
                 "reduceOnly": True, "side": "A",
                 "triggerCondition": "Activation immediate, retracement 5.9583, best 20.931"}
        result = trailing_readback(order, retracement=Decimal("5.9583"))
        self.assertTrue(result["active"])
        self.assertEqual(result["trigger_price"], "14.9727")
        for condition in (
            "activation immediate, activation immediate, retracement 5.9583",
            "activation immediate, activation above 20, retracement 5.9583",
            "activation above 20, activation immediate, retracement 5.9583",
            "activation unknown, retracement 5.9583",
        ):
            with self.subTest(condition=condition), self.assertRaises(ValueError):
                trailing_readback(order | {"triggerCondition": condition}, retracement=Decimal("5.9583"))

    def test_known_syntax_is_distinct_from_managed_semantic_matching(self):
        from kis_hl.hyperliquid.trailing import parse_trailing_condition, trailing_readback
        result = parse_trailing_condition("retracement 5.0000%, activation above 100, best waiting")
        self.assertEqual(result["retracement_unit"], "percent")
        self.assertEqual(result["activation_price"], "100")
        self.assertFalse(result["active"])
        order = {"orderType": "Trailing Stop Market", "isTrigger": True, "reduceOnly": True, "side": "A"}
        result = trailing_readback(order | {"triggerCondition": "retracement 4"}, retracement=Decimal("4"))
        self.assertFalse(result["active"])
        for condition, reason in [("retracement 4%, best 104", "retracement mismatch"),
                                  ("retracement 4, activation below 100, best 104", "activation mismatch")]:
            with self.subTest(condition=condition), self.assertRaisesRegex(ValueError, reason):
                trailing_readback(order | {"triggerCondition": condition}, retracement=Decimal("4"))
        for condition in ("retracement 4, best NaN", "retracement 4, best waiting, best 104",
                          "retracement 4, activation above 100, activation below 90",
                          "retracement 4, activation above NaN", "retracement 4, unknown 3",
                          "retracement 100%, best 104", "best 104"):
            with self.subTest(condition=condition), self.assertRaises(ValueError):
                parse_trailing_condition(condition)

    def test_distance_precision_uses_value_not_market_price(self):
        from kis_hl.hyperliquid.trailing import normalize_quote_retracement
        for raw, tick, expected in [("4", ".1", "4"), ("4.246912", ".0001", "4.2469"),
                                    ("123.456", ".0001", "123.45"), ("123456", ".1", "123456")]:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_quote_retracement(Decimal(raw), Decimal(tick)), Decimal(expected))
        with self.assertRaises(ValueError):
            normalize_quote_retracement(Decimal("0.01"), Decimal("0.1"))

    def test_readback_is_strict_and_computes_mark_threshold(self):
        from kis_hl.hyperliquid.trailing import trailing_readback
        order = {"orderType": "Trailing Stop Market", "isTrigger": True, "reduceOnly": True,
            "side": "A", "triggerCondition": "retracement 4, best 104"}
        result = trailing_readback(order, retracement=Decimal("4"))
        self.assertEqual(result["trigger_price"], "100")
        for change in ({"orderType": "Stop Market"}, {"reduceOnly": False},
            {"triggerCondition": "retracement 5, best 104"},
            {"triggerCondition": "retracement 4, best NaN"},
            {"triggerCondition": "retracement 4, best 104, unknown 3"}):
            with self.subTest(change=change), self.assertRaises(ValueError): trailing_readback(order | change, retracement=Decimal("4"))
        self.assertFalse(trailing_readback(order | {"triggerCondition": "retracement 4, best waiting"}, retracement=Decimal("4"))["active"])

class NativeTrailingGatewayTests(unittest.TestCase):
    def fixture(self):
        from tests import test_managed_gateways
        g, info, row, attempts, order = test_managed_gateways.ManagedGatewayTests().hl()
        attempts.append({"id": "local-attempt", "order_id": "43", "kind": "trailing", "status": "SUBMITTED", "quantity": "1", "retracement": "4"})
        trailing = {"oid": 43, "coin": "BTC", "side": "A", "sz": "1", "origSz": "1", "reduceOnly": True, "isTrigger": True,
                    "orderType": "Trailing Stop Market", "triggerCondition": "retracement 4, best 104"}
        info.order_status.side_effect = lambda **kw: {"status": "order", "order": {"status": "filled" if kw["oid"] == "0x123" else "open", "order": order if kw["oid"] == "0x123" else trailing}}
        info.frontend_open_orders.return_value = [trailing]
        return g, info, row, attempts, trailing

    def test_condition_parse_failure_preserves_known_order_and_account_snapshot(self):
        for condition in (None, "new exchange format", "retracement 4, best NaN"):
            g, _, row, attempts, trailing = self.fixture()
            trailing["triggerCondition"] = condition
            with self.subTest(condition=condition):
                snap = g.snapshot(row, attempts, 20)
                observed = snap["orders"]["43"]
                self.assertEqual(observed["status"], "open")
                self.assertTrue(observed["trailing_readback_error"])
                self.assertNotIn("active", observed)
                self.assertTrue(snap["consistent"])
                self.assertFalse(snap["foreign_add"])

    def test_condition_error_does_not_hide_identity_type_side_or_size_mismatch(self):
        for change in ({"coin": "ETH"}, {"oid": 44}, {"side": "B"},
                       {"reduceOnly": False}, {"isTrigger": False},
                       {"orderType": "Limit"}, {"sz": "2"}, {"sz": "-1"}):
            g, _, row, attempts, trailing = self.fixture()
            trailing.update(triggerCondition="unknown syntax", **change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                g.snapshot(row, attempts, 20)

    def test_native_oid_readback_without_cloid_and_owned_open_order(self):
        g, info, row, attempts, trailing = self.fixture()
        snap = g.snapshot(row, attempts, 20)
        self.assertFalse(snap["foreign_add"])
        self.assertEqual(snap["orders"]["43"]["trigger_price"], "100")
        self.assertTrue(snap["orders"]["43"]["active"])

    def test_gateway_keeps_decimal_tick_separate_from_quote_grid(self):
        g, info, row, attempts, _ = self.fixture()
        info.meta_and_asset_ctxs.return_value[0]["universe"][0]["szDecimals"] = 5
        info.l2_book.return_value["levels"] = [[{"px": "100000"}], [{"px": "100000.1"}]]
        snap = g.snapshot(row, attempts, 20)
        self.assertEqual(Decimal(snap["price_step"]), Decimal("10"))
        self.assertEqual(Decimal(snap["trailing_price_step"]), Decimal("0.1"))

    def test_gateway_accepts_omitted_best_as_waiting_but_rejects_activation(self):
        g, _, row, attempts, trailing = self.fixture()
        trailing["triggerCondition"] = "retracement 4"
        self.assertFalse(g.snapshot(row, attempts, 20)["orders"]["43"]["active"])
        g, _, row, attempts, trailing = self.fixture()
        trailing["triggerCondition"] = "retracement 4, activation above 100, best waiting"
        with self.assertRaisesRegex(ValueError, "activation mismatch"):
            g.snapshot(row, attempts, 20)

    def test_unknown_ack_never_adopts_matching_order(self):
        g, info, row, attempts, _ = self.fixture()
        attempts[-1]["order_id"] = None
        snap = g.snapshot(row, attempts, 20)
        self.assertTrue(snap["foreign_add"])
        self.assertNotIn("43", snap["orders"])
        self.assertEqual(info.order_status.call_count, 1)

    def test_wrong_distance_coin_and_oversized_order_are_rejected(self):
        for changes in ({"coin": "ETH"}, {"triggerCondition": "retracement 5, best 104"}, {"sz": "2"}, {"oid": 44}):
            g, _, row, attempts, trailing = self.fixture()
            trailing.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                g.snapshot(row, attempts, 20)

    def test_native_submit_calls_distinct_action_without_cloid(self):
        g, _, row, attempts, _ = self.fixture()
        g.trading.place_trailing_stop_order.return_value = SimpleNamespace(status="unknown", response={"status": "ok"})
        a = attempts[-1] | {"created_ms": 10}
        result = g.submit(row, a)
        self.assertEqual(result, {"status": "unknown", "order_id": None})
        self.assertNotIn("cloid", g.trading.place_trailing_stop_order.call_args.kwargs)
        g.trading.place_order.assert_not_called()
