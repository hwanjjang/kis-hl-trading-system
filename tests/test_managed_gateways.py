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
            "levels": [[{"px": "100"}], [{"px": "100.1"}]],
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
