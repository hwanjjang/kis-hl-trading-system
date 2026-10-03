import unittest
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from kis_hl.managed_gateways import ManagedHyperliquidGateway, ManagedKisGateway
from kis_hl.instruments import instrument
from tests.test_managed_execution import plan


class ManagedGatewayTests(unittest.TestCase):
    def test_sqlite_eligibility_is_required_even_for_documented_xyz_assets(self):
        import tempfile
        import sqlite3
        from pathlib import Path
        from kis_hl.storage import seed_trade_xyz_assets
        from kis_hl.assets import resolve_hyperliquid_symbol

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "state.sqlite"
            seed_trade_xyz_assets(path)
            g, _, _, _, _ = self.hl()
            g.trading.verification_db_path = path
            resolved = resolve_hyperliquid_symbol("xyz:SP500")
            self.assertTrue(g._eligible(resolved))
            with sqlite3.connect(path) as db:
                db.execute(
                    "UPDATE trade_xyz_assets SET tradable=0 WHERE hyperliquid_coin='xyz:SP500'"
                )
            self.assertFalse(g._eligible(resolved))

    def hl(self):
        info = Mock()
        info.config = SimpleNamespace(
            base_url="https://api.hyperliquid-testnet.xyz", account_address="fixture"
        )
        info.meta_and_asset_ctxs.return_value = [
            {"universe": [{"name": "BTC", "szDecimals": 2}]},
            [],
        ]
        info.frontend_open_orders.return_value = []
        info.clearinghouse_state.return_value = {
            "assetPositions": [
                {
                    "position": {
                        "coin": "BTC",
                        "szi": "1",
                        "entryPx": "100",
                        "positionValue": "100",
                    }
                }
            ],
            "withdrawable": "1000",
        }
        info.active_asset_data.return_value = {"maxTradeSzs": ["10", "10"], "availableToTrade": ["1000", "1000"]}
        info.user_fills_by_time.return_value = [
            {
                "tid": 1,
                "coin": "BTC",
                "side": "B",
                "sz": "1",
                "px": "100",
                "time": 10,
                "oid": 42,
            }
        ]
        info.l2_book.return_value = {
            "time": 20,
            "levels": [[{"px": "100", "sz": "10"}], [{"px": "100.1", "sz": "10"}]],
        }
        order = {
            "oid": 42,
            "cloid": "0x123",
            "coin": "BTC",
            "sz": "0",
            "origSz": "1",
            "side": "B",
            "reduceOnly": False,
            "isTrigger": False,
            "orderType": "Limit",
        }
        info.order_status.return_value = {
            "status": "order",
            "order": {"status": "filled", "order": order},
        }
        gateway = ManagedHyperliquidGateway(info, Mock())
        row = {"created_ms": 1, "plan": plan()}
        attempts = [
            {"id": "0x123", "kind": "entry", "order_id": None, "status": "UNKNOWN"}
        ]
        return gateway, info, row, attempts, order

    def test_unknown_ack_resolves_by_client_id_and_actual_fills(self):
        g, info, row, attempts, order = self.hl()
        s = g.snapshot(row, attempts, 20)
        self.assertTrue(s["consistent"])
        self.assertFalse(s["foreign_add"])
        self.assertEqual(s["entry_filled"], "1")
        self.assertEqual(s["orders"]["0x123"]["native_id"], "42")
        self.assertEqual(s["first_fill_time_ms"], 10)

    def test_snapshot_cutoff_is_fresh_even_when_tick_predates_fill(self):
        g, info, row, attempts, _ = self.hl()
        info.user_fills_by_time.return_value[0]["time"] = 28
        with patch("kis_hl.managed_gateways.time.time", return_value=0.030):
            snap = g.snapshot(row, attempts, 20)
        self.assertTrue(snap["consistent"])
        self.assertEqual(snap["entry_filled"], "1")
        info.user_fills_by_time.assert_called_once_with(start_time_ms=1, end_time_ms=30)
        self.assertEqual(snap["reconciliation_context"]["tick_ms"], 20)
        self.assertEqual(snap["reconciliation_context"]["fill_cutoff_ms"], 30)

    def test_fill_between_history_and_exposure_converges_by_full_readback(self):
        g, info, row, attempts, order = self.hl()
        clock = [20]
        fill = dict(info.user_fills_by_time.return_value[0], time=28)
        info.user_fills_by_time.side_effect = lambda **kw: [fill] if kw["end_time_ms"] >= 28 else []
        state = info.clearinghouse_state.return_value
        def exposure(**kw):
            clock[0] = 30  # The authorized fill arrives after the history read.
            return state
        info.clearinghouse_state.side_effect = exposure
        order["sz"] = "1"
        info.order_status.side_effect = [
            {"status": "order", "order": {"status": "open", "order": dict(order)}},
            {"status": "order", "order": {"status": "filled", "order": dict(order, sz="0")}},
        ]
        with patch("kis_hl.managed_gateways.time.time", side_effect=lambda: clock[0] / 1000):
            snap = g.snapshot(row, attempts, 20)
        self.assertTrue(snap["consistent"])
        self.assertEqual(snap["reconciliation_context"]["fill_cutoff_ms"], 30)
        self.assertEqual([c.kwargs["end_time_ms"] for c in info.user_fills_by_time.call_args_list], [20, 30])
        self.assertEqual(snap["reconciliation_context"]["readback_attempt"], 2)
        self.assertEqual(info.order_status.call_count, 2)
        self.assertEqual(info.frontend_open_orders.call_count, 2)
        self.assertEqual(info.clearinghouse_state.call_count, 2)
        # Snapshot discovery must not mutate the caller's durable attempt view.
        self.assertIsNone(attempts[0]["order_id"])

    def test_terminal_entry_with_missing_fills_is_not_consistent_flat(self):
        g, info, row, attempts, _ = self.hl()
        info.user_fills_by_time.return_value = []
        info.clearinghouse_state.return_value["assetPositions"] = []
        snap = g.snapshot(row, attempts, 20)
        self.assertFalse(snap["consistent"])
        self.assertEqual(info.user_fills_by_time.call_count, 3)
        self.assertEqual(snap["reconciliation_context"]["mismatch"], "order_fills")

    def test_snapshot_mismatch_readback_is_bounded_and_remains_unsafe(self):
        g, info, row, attempts, _ = self.hl()
        info.user_fills_by_time.return_value = []
        snap = g.snapshot(row, attempts, 20)
        self.assertFalse(snap["consistent"])
        self.assertEqual(info.user_fills_by_time.call_count, 3)
        self.assertEqual(snap["reconciliation_context"]["readback_attempt"], 3)

    def test_external_protections_are_never_adopted_or_retried_away(self):
        for kind in ("Stop Market", "Trailing Stop Market"):
            with self.subTest(kind=kind):
                g, info, row, attempts, _ = self.hl()
                info.frontend_open_orders.return_value = [dict(coin="BTC", oid=99,
                    side="A", sz="1", reduceOnly=True, orderType=kind)]
                snap = g.snapshot(row, attempts, 20)
                self.assertTrue(snap["foreign_add"])
                self.assertEqual(info.frontend_open_orders.call_count, 1)
                self.assertNotIn("99", snap["orders"])

    def test_verified_exact_external_ids_still_require_explicit_latch_recovery(self):
        import tempfile
        from pathlib import Path
        from kis_hl.managed_execution import ExecutionStore, Supervisor

        g, info, _, _, entry = self.hl()
        stop = dict(entry, oid=43, side="A", reduceOnly=True, isTrigger=True,
                    orderType="Stop Market", sz="1", triggerPx="96")
        trailing = dict(stop, oid=44, orderType="Trailing Stop Market",
                        triggerCondition="Activation immediate, retracement 4, best 104")
        info.frontend_open_orders.return_value = [stop, trailing]
        info.order_status.side_effect = lambda *, oid: {"status": "order", "order": {
            "status": "filled" if oid == 42 else "open",
            "order": {42: entry, 43: stop, 44: trailing}[oid]}}
        with tempfile.TemporaryDirectory() as temp:
            store = ExecutionStore(Path(temp) / "state.sqlite")
            row = store.enqueue(g.scope, plan(), live=True, now_ms=1)
            row["state"] = "ENTERING"
            store.save(row, 2)
            attempt = store.attempt(row, "entry", 2, quantity="1", price="100")
            store.update_attempt(attempt, order_id="42", status="SUBMITTED")
            worker = Supervisor(store, g, live=True)
            with patch("kis_hl.managed_gateways.time.time", return_value=0.030):
                result = worker.step(row["id"], 20)
            self.assertEqual(result["state"], "INTERVENTION")
            self.assertIsNone(result["trail"])
            self.assertFalse(g.trading.place_order.called)
            # Simulate a separately reviewed exact-ID binding in this offline DB.
            # This does not add or authorize a production recovery command.
            for kind, oid, values in (("stop", "43", {"trigger_price": "96"}),
                                      ("trailing", "44", {"retracement": "4"})):
                a = store.attempt(result, kind, 31, quantity="1", price="100", **values)
                store.update_attempt(a, order_id=oid, status="SUBMITTED")
            with patch("kis_hl.managed_gateways.time.time", return_value=0.040):
                snap = g.snapshot(result, store.attempts(row["id"]), 40)
                self.assertTrue(snap["consistent"])
                self.assertFalse(snap["foreign_add"])
                result = worker.step(row["id"], 40)
            self.assertEqual(result["state"], "INTERVENTION")
            self.assertIsNone(result["trail"])
            # Even verified IDs alone cannot silently clear generic intervention.
            result["state"] = "ENTERING"
            store.save(result, 41)
            with patch("kis_hl.managed_gateways.time.time", return_value=0.050):
                result = worker.step(row["id"], 50)
            self.assertEqual(result["state"], "PROTECTED")
            self.assertEqual(result["covered_size"], "1")
            self.assertFalse(g.trading.place_order.called)
            self.assertFalse(g.trading.place_trailing_stop_order.called)

    def test_stale_open_entry_status_is_refreshed_after_fill(self):
        g, info, row, attempts, order = self.hl()
        info.order_status.side_effect = [
            {"status": "order", "order": {"status": "open", "order": dict(order, sz="1")}},
            info.order_status.return_value,
        ]
        snap = g.snapshot(row, attempts, 20)
        self.assertTrue(snap["consistent"])
        self.assertEqual(info.order_status.call_count, 2)
        self.assertEqual(snap["orders"]["42"]["status"], "filled")

    def test_sp500_immediate_post_submit_fill_initializes_one_sl_and_trailing(self):
        import tempfile
        from pathlib import Path
        from kis_hl.managed_execution import ExecutionStore, Supervisor
        from tests.test_managed_execution import Gateway

        for provider in ("local", "native"):
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as temp:
                g, info, _, _, _ = self.hl()
                coin = "xyz:SP500"
                p = plan() | dict(instrument="hl:xyz:SP500", signal_instrument="hl:xyz:SP500",
                    quantity="0.177", limit_price="7700", atr="61.04", atr_multiple="2",
                    fixed_stop_price="7577", max_notional="1400", max_loss="30",
                    max_portfolio_notional="10000", max_correlated_notional="10000")
                p["trailing_provider"] = provider
                info.meta_and_asset_ctxs.return_value = [{"collateralToken": 0,
                    "universe": [{"name": coin, "szDecimals": 3}]}, []]
                info.l2_book.return_value = {"time": 30,
                    "levels": [[{"px": "7698.7"}], [{"px": "7699"}]]}
                info.clearinghouse_state.return_value["assetPositions"][0]["position"].update(
                    coin=coin, szi="0.177", entryPx="7698.7", positionValue="1362.673")
                fill = dict(tid=1, coin=coin, side="B", sz="0.177", px="7698.7", time=28, oid=42)
                info.user_fills_by_time.side_effect = lambda **kw: [fill] if kw["end_time_ms"] >= 28 else []
                orders = {}
                def submit(**kw):
                    oid = 42 if kw["side"] == "buy" else 43
                    order = dict(oid=oid, cloid=kw["cloid"], coin=coin,
                        origSz=str(kw["size"]), sz="0" if oid == 42 else str(kw["size"]),
                        side="B" if oid == 42 else "A", reduceOnly=oid != 42,
                        isTrigger=oid != 42, orderType="Limit" if oid == 42 else "Stop Market",
                        triggerPx=str(kw.get("trigger_price") or 0))
                    orders[str(oid)] = {"status": "order", "order": {
                        "status": "filled" if oid == 42 else "open", "order": order}}
                    return SimpleNamespace(status="submitted", response={"response": {"data": {
                        "statuses": [{"filled" if oid == 42 else "resting": {"oid": oid}}]}}})
                def trailing(**kw):
                    orders["44"] = {"status": "order", "order": {"status": "open", "order": dict(
                        oid=44, coin=coin, side="A", reduceOnly=True, isTrigger=True, sz=str(kw["size"]),
                        orderType="Trailing Stop Market", triggerCondition=(
                            f"Activation immediate, retracement {kw['retracement']}, best 7698.7"))}}
                    return SimpleNamespace(status="submitted", response={"response": {"data": {
                        "statuses": [{"resting": {"oid": 44}}]}}})
                g.trading.place_order.side_effect = submit
                g.trading.place_trailing_stop_order.side_effect = trailing
                info.order_status.side_effect = lambda *, oid: orders[str(oid)]
                info.frontend_open_orders.side_effect = lambda **kw: [
                    r["order"]["order"] for r in orders.values() if r["order"]["status"] == "open"]
                pre = Gateway().preflight(p, 23) | {"entry_order_type": "limit",
                    "observed_now_ms": 23, "price": "7700",
                    "ask": "7701", "available_notional": "10000", "atr": "61.04",
                    "quantity_step": "0.001", "trailing_price_step": "0.001"}
                g.preflight = Mock(return_value=pre)
                store = ExecutionStore(Path(temp) / "state.sqlite")
                row = store.enqueue(g.scope, p, live=True, now_ms=1)
                worker = Supervisor(store, g, live=True)
                worker.step(row["id"], 20)  # intent/attempt at 23, fill at 28
                # Emulate the IOC caller's same-tick post-submit readback. Routing
                # is deliberately independent: this bug affects any filled entry.
                with patch("kis_hl.managed_gateways.time.time", return_value=0.030):
                    result = worker.step(row["id"], 20)
                    self.assertNotEqual(result["state"], "INTERVENTION")
                    self.assertEqual(result["entry_filled"], "0.177")
                    self.assertEqual(result["first_fill_ms"], 28)
                    self.assertIsNotNone(result["trail"])
                    self.assertEqual([a["kind"] for a in store.attempts(row["id"])], ["entry", "stop"])
                    for now in (31, 32, 33):
                        result = Supervisor(store, g, live=True).step(row["id"], now)
                self.assertEqual(result["state"], "PROTECTED", result["reason"])
                self.assertEqual(result["covered_size"], "0.177")
                self.assertEqual(g.trading.place_order.call_count, 2)
                self.assertEqual(g.trading.place_trailing_stop_order.call_count, int(provider == "native"))
                self.assertTrue(all(a.get("order_id") for a in store.attempts(row["id"])))

    def test_owned_add_fills_remain_owned_and_partial_protective_fill_is_reported(self):
        g, info, row, attempts, order = self.hl()
        attempts[0]["kind"] = "add"
        stop = dict(order, oid=43, side="A", reduceOnly=True, isTrigger=True,
                    orderType="Stop Market", sz="0.8", triggerPx="96")
        attempts.append(dict(id="stop", kind="stop", order_id="43", status="SUBMITTED"))
        info.order_status.side_effect = lambda *, oid: {"status": "order", "order": {
            "status": "open" if str(oid) == "43" else "filled",
            "order": stop if str(oid) == "43" else order}}
        info.user_fills_by_time.return_value.append(dict(tid=2, coin="BTC", side="A",
            sz="0.2", px="96", time=11, oid=43))
        info.clearinghouse_state.return_value["assetPositions"][0]["position"]["szi"] = "0.8"
        snap = g.snapshot(row, attempts, 20)
        self.assertTrue(snap["consistent"])
        self.assertFalse(snap["foreign_add"])
        self.assertEqual(snap["fills_by_attempt"]["0x123"], "1")
        self.assertEqual(snap["protective_filled"], "0.2")

    def test_add_transport_is_bounded_buy_with_durable_client_id(self):
        g, info, row, _, _ = self.hl()
        row["plan"]["max_quote_age_ms"] = 1000
        g.trading.place_order.return_value = SimpleNamespace(status="submitted", response={})
        g.submit(row, dict(id="0x123", kind="add", quantity="0.5", price="100",
                           created_ms=10, expires_ms=20))
        call = g.trading.place_order.call_args.kwargs
        self.assertEqual(call["side"], "buy")
        self.assertFalse(call["reduce_only"])
        self.assertEqual(call["cloid"], "0x123")
        self.assertEqual(call["expires_after_ms"], 20)

    def test_full_size_book_selects_market_or_current_ask_limit(self):
        g, info, row, _, _ = self.hl()
        from kis_hl.assets import resolve_hyperliquid_symbol
        resolved = resolve_hyperliquid_symbol("BTC-PERP")
        for asks, expected in [
            ([{"px": "100.1", "sz": "1"}], "market"),
            ([{"px": "100.1", "sz": "0.5"}, {"px": "101", "sz": "0.5"}], "limit"),
            ([{"px": "100.1", "sz": "0.5"}], "limit"),
            ([{"px": "100.6", "sz": "1"}], "limit"),
        ]:
            with self.subTest(asks=asks):
                info.l2_book.return_value = {"time": 20, "levels": [[{"px": "100", "sz": "1"}], asks]}
                bid, ask, _, route = g._entry_quote(resolved, Decimal("1"))
                self.assertEqual((bid, ask, route), (Decimal("100"), Decimal(asks[0]["px"]), expected))

    def test_market_entry_transport_retains_cloid_and_half_percent_cap(self):
        g, info, row, _, _ = self.hl()
        row["plan"]["max_quote_age_ms"] = 1000
        g.trading.place_order.return_value = SimpleNamespace(status="submitted", response={})
        g.submit(row, dict(id="0x123", kind="entry", quantity="1", price="100.5",
                           order_type="market", created_ms=10))
        call = g.trading.place_order.call_args.kwargs
        self.assertEqual((call["order_type"], call["tif"], call["price"]),
                         ("limit", "Ioc", Decimal("100.5")))
        self.assertEqual(call["cloid"], "0x123")
        self.assertFalse(call["reduce_only"])

    def test_limit_only_entry_transport_is_capped_limit_order(self):
        g, info, row, _, _ = self.hl()
        row["plan"]["entry_route"] = "limit"
        g.trading.place_order.return_value = SimpleNamespace(status="submitted", response={})
        g.submit(row, dict(id="0x123", kind="entry", quantity="1", price="100.1",
                           order_type="limit", created_ms=10, expires_ms=20))
        call = g.trading.place_order.call_args.kwargs
        self.assertEqual((call["order_type"], call["price"], call["tif"]),
                         ("limit", Decimal("100.1"), "Gtc"))
        self.assertEqual(call["expires_after_ms"], 20)

    def test_market_route_signs_exact_cap_even_if_sdk_mid_moves(self):
        from tests.test_hyperliquid_client import ExchangeSafetyTests
        from hyperliquid.exchange import Exchange
        for mid in ("100.05", "200"):
            with self.subTest(mid=mid):
                g, _, row, _, _ = self.hl()
                g.trading = ExchangeSafetyTests().client()
                exchange = g.trading._sdk[1]
                exchange.info.name_to_coin = {"BTC": "BTC"}
                exchange.info.coin_to_asset = {"BTC": 0}
                exchange.info.asset_to_sz_decimals = {0: 2}
                exchange.info.all_mids.return_value = {"BTC": mid}
                exchange._slippage_price.side_effect = lambda *a: Exchange._slippage_price(exchange, *a)
                exchange.market_open.side_effect = lambda *a, **kw: Exchange.market_open(exchange, *a, **kw)
                exchange.order.return_value = {"status": "ok", "response": {"data": {"statuses": [{"filled": {"oid": 42}}]}}}
                with patch("kis_hl.managed_gateways.time.time", return_value=.011), patch(
                        "kis_hl.hyperliquid.client.time.time", return_value=.011), patch(
                        "kis_hl.hyperliquid.client.sdk_cloid", side_effect=lambda x: x):
                    g.submit(row, dict(id="0x"+"a"*32, kind="entry", quantity="1", price="100.50",
                                       order_type="market", created_ms=10))
                self.assertEqual(exchange.order.call_args.args[:6],
                    ("BTC", True, 1.0, 100.5, {"limit": {"tif": "Ioc"}}, False))
                exchange.market_open.assert_not_called()
                exchange.info.all_mids.assert_not_called()

    def test_entry_preflight_uses_instrument_buying_power_not_dex_withdrawable(self):
        g, info, row, _, _ = self.hl()
        info.clearinghouse_state.return_value["withdrawable"] = "0.0"
        info.active_asset_data.return_value = {"maxTradeSzs": ["2", "3"], "availableToTrade": ["200", "300"]}
        with patch("kis_hl.trailing_runner.fetch_trailing_atr", return_value=(Decimal(2), [{"T": 10}])):
            snap = g.preflight(row["plan"], 20)
        self.assertEqual(snap["available_notional"], "200")
        self.assertNotIn("capital_evidence", snap)
        info.active_asset_data.assert_called_once_with("BTC")

    def test_explicit_limit_only_entry_never_routes_to_market(self):
        g, info, row, _, _ = self.hl()
        row["plan"]["entry_route"] = "limit"
        info.l2_book.return_value = {"time": 20, "levels": [
            [{"px": "100", "sz": "1"}], [{"px": "100.1", "sz": "10"}]]}
        with patch("kis_hl.trailing_runner.fetch_trailing_atr", return_value=(Decimal(2), [{"T": 10}])):
            snap = g.preflight(row["plan"], 20)
        self.assertEqual(snap["entry_order_type"], "limit")

    def test_add_preflight_collects_total_balance_separately_from_buying_power(self):
        g, info, row, _, _ = self.hl()
        info.user_abstraction.return_value = "unifiedAccount"
        info.spot_clearinghouse_state.return_value = {"balances": [{"coin": "USDC", "token": 0, "total": "1000"}]}
        info.active_asset_data.return_value = {"maxTradeSzs": ["2", "3"], "availableToTrade": ["200", "300"]}
        p = {**row["plan"], "action": "add"}
        with patch("kis_hl.trailing_runner.fetch_trailing_atr", return_value=(Decimal(2), [{"T": 10}])):
            snap = g.preflight(p, 20)
        self.assertEqual(snap["capital_evidence"]["scope"], g.scope)
        self.assertEqual(snap["capital_evidence"]["spot"]["balances"][0]["total"], "1000")
        self.assertEqual(snap["available_notional"], "200")
        info.active_asset_data.assert_called_once_with("BTC")
        info.user_abstraction.assert_called_once_with()


    def test_native_order_identity_mismatch_is_rejected(self):
        for change in [{"cloid": "0xOTHER"}, {"side": "A"}, {"reduceOnly": True}]:
            with self.subTest(change=change):
                g, info, row, attempts, order = self.hl()
                order.update(change)
                with self.assertRaises(ValueError):
                    g.snapshot(row, attempts, 20)

    def test_missing_book_does_not_hide_execution_evidence(self):
        g, info, row, attempts, _ = self.hl()
        info.l2_book.side_effect = TimeoutError()
        s = g.snapshot(row, attempts, 20)
        self.assertEqual(s["size"], "1")
        self.assertEqual(s["time_ms"], 0)

    def test_foreign_increase_is_not_adopted(self):
        g, info, row, attempts, _ = self.hl()
        info.user_fills_by_time.return_value[0]["oid"] = 99
        self.assertTrue(g.snapshot(row, attempts, 20)["foreign_add"])

    def test_filled_stop_readback_without_trigger_flag_is_still_owned_stop(self):
        # Hyperliquid reports a triggered/filled Stop Market with isTrigger=false.
        g, info, row, attempts, order = self.hl()
        attempts[0]["kind"] = "stop"
        order.update(side="A", reduceOnly=True, isTrigger=False,
                     orderType="Stop Market", sz="0.0", triggerPx="0.0")
        snap = g.snapshot(row, attempts, 20)
        self.assertEqual(snap["orders"]["0x123"]["kind"], "stop")
        order["orderType"] = "Take Profit Market"
        with self.assertRaises(ValueError):
            g.snapshot(row, attempts, 20)

    def test_stop_contract_is_bound_to_sell_reduce_only_stop_market(self):
        g, info, row, attempts, order = self.hl()
        attempts[0]["kind"] = "stop"
        order.update(
            side="A",
            reduceOnly=True,
            isTrigger=True,
            orderType="Take Profit Market",
            triggerPx="96",
        )
        with self.assertRaises(ValueError):
            g.snapshot(row, attempts, 20)

    def kis(self):
        client = Mock()
        client.config = SimpleNamespace(
            base_url="https://fixture", account_id="fixture", mode="live"
        )
        return ManagedKisGateway(client), client

    def test_overseas_quote_uses_broker_clock_and_catalog_identity(self):
        g, c = self.kis()
        c.order_book.return_value = SimpleNamespace(
            status=200,
            body={
                "rt_cd": "0",
                "output1": {
                    "code": "SPY",
                    "curr": "USD",
                    "dymd": "20260911",
                    "dhms": "223100",
                },
                "output2": {"pbid1": "100", "pask1": "100.1"},
            },
        )
        bid, ask, stamp = g._quote(instrument("kis:SPY"))
        self.assertEqual(
            stamp,
            int(datetime(2026, 9, 11, 13, 31, tzinfo=timezone.utc).timestamp() * 1000),
        )
        c.order_book.return_value.body["output1"]["code"] = "QQQ"
        with self.assertRaises(ValueError):
            g._quote(instrument("kis:SPY"))

    def test_kis_cancel_uses_persisted_organization_and_remaining_quantity(self):
        g, c = self.kis()
        row = {"plan": {"instrument": "kis:069500"}}
        g.cancel(row, {"target_id": "123", "quantity": "2", "organization_id": "345"})
        self.assertEqual(c.revise_cash_order.call_args.kwargs["quantity"], "2")
        self.assertEqual(c.revise_cash_order.call_args.kwargs["organization_id"], "345")
        c.account_pages.assert_not_called()

    def test_kis_cumulative_fill_is_not_readded_each_poll(self):
        g, c = self.kis()
        history = [
            {
                "pdno": "069500",
                "odno": "123",
                "tot_ccld_qty": "2",
                "sll_buy_dvsn_cd": "02",
                "ord_qty": "3",
                "cncl_yn": "N",
            }
        ]
        g._history = lambda *a: history
        g._rows = lambda *a: [
            {
                "pdno": "069500",
                "hldg_qty": "2",
                "pchs_avg_pric": "100",
                "ord_psbl_qty": "2",
            }
        ]
        g._quote = lambda *a: (Decimal("100"), Decimal("101"), 20)
        g._session = lambda *a: True
        c.account_pages.return_value = {"output": []}
        row = {
            "created_ms": 1,
            "plan": {"instrument": "kis:069500", "verified_price_step": "5"},
            "baseline": {},
        }
        attempts = [{"id": "a", "kind": "entry", "order_id": "123"}]
        for _ in range(2):
            s = g.snapshot(row, attempts, 20)
            self.assertTrue(s["consistent"])
            self.assertEqual(s["entry_filled"], "2")
            self.assertEqual(s["orders"]["123"]["size"], "1")

    def test_hl_entry_session_is_advisory_outside_underlying_hours(self):
        from datetime import datetime, timezone
        from kis_hl.assets import resolve_hyperliquid_symbol

        info = Mock()
        info.config = SimpleNamespace(base_url="https://api.hyperliquid.xyz", account_address="fixture")
        g = ManagedHyperliquidGateway(info, Mock())
        resolved = resolve_hyperliquid_symbol("xyz:KORU")
        # 2026-09-29 06:30 UTC = 15:30 KST: U.S. cash session closed.
        now = int(datetime(2026, 9, 29, 6, 30, tzinfo=timezone.utc).timestamp() * 1000)
        self.assertTrue(g._session(resolved, now))
        self.assertFalse(g._session_advisory(resolved, now)["allowed"])

    def test_kis_disappeared_open_row_does_not_prove_cancellation(self):
        g, c = self.kis()
        g._history = lambda *a: []
        g._rows = lambda *a: []
        g._quote = lambda *a: (Decimal("100"), Decimal("101"), 20)
        g._session = lambda *a: True
        c.account_pages.return_value = {"output": []}
        s = g.snapshot(
            {"created_ms": 1, "plan": {"instrument": "kis:069500"}},
            [{"id": "a", "kind": "entry", "order_id": "123"}],
            20,
        )
        self.assertEqual(s["orders"], {})


if __name__ == "__main__":
    unittest.main()
