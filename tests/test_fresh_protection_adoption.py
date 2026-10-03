"""Saved 2026-10-02 order shapes; mocked reads and temporary SQLite only."""
import copy
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock
import unittest

from kis_hl.instruments import instrument
from tests.test_managed_execution import plan
from tests import test_manual_adoption


class FreshProtectionAdoptionTests(unittest.TestCase):
    def fixture(self, *, quote=False, stop_changes=None):
        c = test_manual_adoption.ManualAdoptionTests(); c.setUp(); self.addCleanup(c.doCleanups)
        key, coin, qty, entry, floor, best = (("hl:xyz:SP500", "xyz:SP500", "0.177", "7698.7", "7577", "7753.7")
            if quote else ("hl:ETH", "ETH", "0.1807", "2757.8", "2685", "2769.6"))
        stop_id, trail_id = ((563255215836, 563255249667) if quote else (563450890327, 563453817096))
        c.g._market = Mock(return_value=(instrument(key), SimpleNamespace(coin=coin, dex="xyz" if quote else None),
                                        Decimal("0.0001"), Decimal("0.01")))
        c.orders[42]["order"].update(coin=coin, origSz=qty, sz="0")
        stop = dict(oid=stop_id, coin=coin, side="A", reduceOnly=True, isTrigger=True,
                    orderType="Stop Market", sz=qty if quote else "0.0", origSz=qty if quote else "0.0",
                    isPositionTpsl=not quote, triggerPx=floor, triggerCondition=f"Price below {floor}")
        stop.update(stop_changes or {})
        trail = dict(oid=trail_id, coin=coin, side="A", reduceOnly=True, isTrigger=True,
                     orderType="Trailing Stop Market", sz=qty, origSz=qty, isPositionTpsl=False,
                     triggerCondition=f"Activation immediate, retracement {'183.12' if quote else '8.35%'}, best {best}")
        c.orders = {42:c.orders[42], stop_id:dict(status="open", order=stop), trail_id:dict(status="open", order=trail)}
        c.fills[0].update(coin=coin, sz=qty, px=entry)
        c.info.l2_book.return_value["levels"] = [[{"px":entry, "sz":"10"}], [{"px":str(Decimal(entry)+Decimal("0.1")), "sz":"10"}]]
        c.info.clearinghouse_state.return_value = {"assetPositions":[{"position":dict(coin=coin, szi=qty, entryPx=entry)}]}
        c.g.preflight.return_value.update(atr_source={"instrument":key}, atr="61.04" if quote else "2",
                                         open_orders=[stop,trail])
        p = plan() | dict(instrument=key, signal_instrument=key, quantity=qty, limit_price=entry,
                 fixed_stop_price=floor, max_loss="100", max_notional="2000", trailing_provider="native",
                 local_trailing_backup=quote)
        if quote:
            p.update(atr="61.04", native_atr_multiple="3", local_atr_multiple="2")
        else:
            p["native_trailing_percent"] = "8.35"
        return c, p, stop_id, trail_id

    def test_eth_position_level_zero_size_stop_covers_verified_position(self):
        c, p, stop_id, trail_id = self.fixture()
        before = copy.deepcopy(c.orders)
        row = c.store.enqueue_adoption(c.g.scope, p, entry_order_id=42, stop_order_id=stop_id,
                                      trailing_order_id=trail_id, live=True, now_ms=20)
        self.assertEqual(c.step(row)["state"], "PROTECTING")
        result = c.step(row, 22)
        self.assertEqual(result["state"], "PROTECTED")
        self.assertEqual(result["covered_size"], "0.1807")
        self.assertEqual(c.orders, before)
        for method in (c.g.trading.place_order, c.g.trading.place_trailing_stop_order, c.g.trading.cancel_order):
            method.assert_not_called()

    def test_zero_size_without_verified_position_sl_semantics_rejects(self):
        for changes in ({"isPositionTpsl":False}, {"isPositionTpsl":None}, {"isPositionTpsl":1},
                        {"side":"B"}, {"coin":"BTC"}, {"reduceOnly":False}, {"reduceOnly":1},
                        {"isTrigger":False}, {"orderType":"Take Profit Market"}, {"triggerPx":"2684"}):
            with self.subTest(changes=changes):
                c, p, stop_id, trail_id = self.fixture(stop_changes=changes)
                row = c.store.enqueue_adoption(c.g.scope, p, entry_order_id=42, stop_order_id=stop_id,
                                              trailing_order_id=trail_id, live=True, now_ms=20)
                self.assertEqual(c.step(row)["state"], "INTERVENTION")
                self.assertEqual(c.store.attempts(row["id"]), [])
                c.g.trading.place_order.assert_not_called()
                c.g.trading.place_trailing_stop_order.assert_not_called()

    def test_position_sl_coverage_tracks_only_reconciled_owned_added_fills(self):
        c, p, stop_id, trail_id = self.fixture()
        row = c.store.enqueue_adoption(c.g.scope, p, entry_order_id=42, stop_order_id=stop_id,
                                      trailing_order_id=trail_id, live=True, now_ms=20)
        self.assertEqual(c.step(row)["state"], "PROTECTING")
        c.orders[100] = dict(status="filled", order=dict(oid=100, coin="ETH", side="B", reduceOnly=False, sz="0", origSz="0.01"))
        c.store.attempt(row, "add", 22, order_id="100", quantity="0.01", price="2760")
        c.fills.append(dict(c.fills[0], tid=2, oid=100, time=22, sz="0.01", px="2760", startPosition="0.1807"))
        pos = c.info.clearinghouse_state.return_value["assetPositions"][0]["position"]
        pos["szi"] = "0.1907"
        snap = c.g.snapshot(c.store.get(row["id"]), c.store.attempts(row["id"]), 23)
        self.assertEqual(snap["orders"][str(stop_id)]["size"], "0.0")
        self.assertEqual(snap["orders"][str(stop_id)]["coverage_size"], "0.1907")
        pos["szi"] = "0.2"
        snap = c.g.snapshot(c.store.get(row["id"]), c.store.attempts(row["id"]), 23)
        self.assertFalse(snap["consistent"])
        self.assertEqual(snap["orders"][str(stop_id)]["coverage_size"], "0.0")

    def test_quote_reconciliation_rejects_mismatched_exact_readback_without_import(self):
        for changes in ({"oid":99}, {"sz":"0.1"}, {"side":"B"}, {"reduceOnly":False},
                        {"triggerCondition":"Activation immediate, retracement 183.12%, best 7753.7"},
                        {"triggerCondition":"Activation immediate, retracement 184, best 7753.7"},
                        {"triggerCondition":"Activation immediate, retracement 183.12, best waiting"}):
            with self.subTest(changes=changes):
                c, p, stop_id, trail_id = self.fixture(quote=True)
                row = c.store.enqueue_adoption(c.g.scope, p, entry_order_id=42, stop_order_id=stop_id, live=True, now_ms=20)
                self.assertEqual(c.step(row)["state"], "INTERVENTION")
                original_plan = copy.deepcopy(c.store.get(row["id"])["plan"])
                c.store.prepare_external_protection_adoption(row["id"], entry_order_id=42, stop_order_id=stop_id,
                                                             trailing_order_id=trail_id, now_ms=22)
                c.orders[trail_id]["order"].update(changes)
                self.assertEqual(c.step(row, 23)["state"], "INTERVENTION")
                self.assertEqual(c.store.attempts(row["id"]), [])
                self.assertEqual(c.store.get(row["id"])["plan"], original_plan)
                c.g.trading.place_order.assert_not_called()
                c.g.trading.place_trailing_stop_order.assert_not_called()

    def test_sp_quote_owner_reconciliation_preserves_frozen_policy_and_watermarks(self):
        c, p, stop_id, trail_id = self.fixture(quote=True)
        # Original owner did not own the external trailing ID and is in intervention.
        row = c.store.enqueue_adoption(c.g.scope, p, entry_order_id=42, stop_order_id=stop_id, live=True, now_ms=20)
        self.assertEqual(c.step(row)["state"], "INTERVENTION")
        saved = c.store.get(row["id"])
        from kis_hl.trailing import Trail
        trail = Trail.create(entry=Decimal("7698.7"), atr=Decimal("61.04"), multiple=Decimal("2"), opened_ms=10)
        trail.high = Decimal("7753.7"); trail.threshold = Decimal("7631.62")
        saved.update(trail=trail.to_dict(),
                     native_trailing_distance="183.12")
        c.store.save(saved, 22)
        original = copy.deepcopy(saved)
        before = copy.deepcopy(c.orders)
        c.store.prepare_external_protection_adoption(row["id"], entry_order_id=42, stop_order_id=stop_id,
                                                     trailing_order_id=trail_id, now_ms=23)
        # A changing daily ATR does not redefine already authorized protection.
        c.g.preflight.return_value["atr"] = "62"
        self.assertEqual(c.step(row, 24)["state"], "PROTECTING")
        adopted = c.store.get(row["id"])
        self.assertEqual(adopted["plan"], original["plan"])
        self.assertEqual(adopted["trail"], original["trail"])
        self.assertEqual(adopted["native_trailing_distance"], "183.12")
        self.assertEqual(c.store.attempts(row["id"])[-1]["retracement_unit"], "quote")
        self.assertEqual(c.store.attempts(row["id"])[-1]["adopted_readback"]["best_price"], "7753.7")
        self.assertEqual(c.orders, before)
        self.assertEqual(c.step(row, 25)["state"], "PROTECTED")
        attempts = c.store.attempts(row["id"])
        saved = c.store.get(row["id"]); saved["state"] = "INTERVENTION"; c.store.save(saved, 26)
        c.store.prepare_external_protection_adoption(row["id"], entry_order_id=42, stop_order_id=stop_id,
                                                     trailing_order_id=trail_id, now_ms=27)
        self.assertEqual(c.step(row, 28)["state"], "PROTECTING")
        self.assertEqual([a["id"] for a in c.store.attempts(row["id"])], [a["id"] for a in attempts])
        self.assertEqual(c.step(row, 29)["state"], "PROTECTED")
        c.g.trading.place_order.assert_not_called()
        c.g.trading.place_trailing_stop_order.assert_not_called()

    def test_existing_owner_reconciles_actual_average_without_rewriting_entry_limit(self):
        c, p, stop_id, trail_id = self.fixture(quote=True)
        p["limit_price"] = "7700"
        row = c.store.enqueue_adoption(c.g.scope, p, entry_order_id=42, stop_order_id=stop_id, live=True, now_ms=20)
        self.assertEqual(c.step(row)["state"], "INTERVENTION")
        c.store.prepare_external_protection_adoption(row["id"], entry_order_id=42, stop_order_id=stop_id,
                                                     trailing_order_id=trail_id, now_ms=23)
        self.assertEqual(c.step(row, 24)["state"], "PROTECTING")
        self.assertEqual(c.store.get(row["id"])["plan"]["limit_price"], "7700")
        self.assertEqual(c.store.get(row["id"])["trail"]["entry"], "7698.7")


if __name__ == "__main__":
    unittest.main()
