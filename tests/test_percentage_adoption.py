"""Exact-ID external percentage protection import; all transport is mocked."""
import copy
import unittest
from unittest.mock import patch
from tests import test_manual_adoption


class PercentageAdoptionTests(unittest.TestCase):
    def setUp(self):
        self.c = test_manual_adoption.ManualAdoptionTests(); self.c.setUp()
        self.addCleanup(self.c.doCleanups)
        self.c.orders[99] = {"status": "open", "order": dict(oid=99, coin="BTC", side="A",
            reduceOnly=True, isTrigger=True, sz="1", orderType="Trailing Stop Market",
            triggerCondition="retracement 8.35%, best 105")}
        self.c.g.preflight.return_value["open_orders"].append(self.c.orders[99]["order"])

    def queue(self):
        from tests.test_managed_execution import plan
        return self.c.store.enqueue_adoption(self.c.g.scope,
            plan(trailing_provider="native", local_trailing_backup=False,
                 native_trailing_percent="8.35", fixed_stop_price="96"),
            entry_order_id=42, stop_order_id=43, trailing_order_id=99, live=True, now_ms=20)

    def test_new_entry_cannot_use_external_percentage_policy(self):
        from tests.test_managed_execution import plan
        with self.assertRaises(ValueError):
            self.c.store.enqueue(self.c.g.scope, plan(trailing_provider="native",
                native_trailing_percent="8.35", fixed_stop_price="96", local_trailing_backup=False),
                live=True, now_ms=20)

    def test_import_preserves_ids_watermark_and_never_sends(self):
        row = self.queue(); before = copy.deepcopy(self.c.orders)
        result = self.c.step(row)
        self.assertEqual(result["state"], "PROTECTING")
        result = self.c.step(row, 22)
        self.assertEqual(result["state"], "PROTECTED")
        self.assertEqual([a["order_id"] for a in self.c.store.attempts(row["id"])], ["42", "43", "99"])
        self.assertEqual(self.c.orders, before)
        self.c.g.trading.place_order.assert_not_called()
        self.c.g.trading.place_trailing_stop_order.assert_not_called()

    def test_float_percentage_import_preserves_exact_native_orders(self):
        self.c.orders[99]["order"]["triggerCondition"] = (
            "Activation immediate, retracement 8.350000000000001%, best 105")
        row = self.queue(); before = copy.deepcopy(self.c.orders)
        self.assertEqual(self.c.step(row)["state"], "PROTECTING")
        self.assertEqual(self.c.step(row, 22)["state"], "PROTECTED")
        self.assertEqual(self.c.orders, before)
        self.c.g.trading.place_order.assert_not_called()
        self.c.g.trading.place_trailing_stop_order.assert_not_called()

    def test_existing_intervention_owner_migrates_in_place(self):
        row = self.c.queue(local_trailing_backup=False, fixed_stop_price="96")
        self.assertEqual(self.c.step(row)["state"], "INTERVENTION")
        migrated = self.c.store.prepare_external_percentage_adoption(row["id"],
            entry_order_id=42, stop_order_id=43, trailing_order_id=99,
            percent="8.35", now_ms=22)
        self.assertEqual(migrated["id"], row["id"])
        self.assertEqual(self.c.step(row, 23)["state"], "PROTECTING")
        self.assertEqual(len(self.c.store.list()), 1)
        self.c.g.trading.place_order.assert_not_called()

    def test_migration_preserves_existing_local_attempt_ids(self):
        row = self.queue(); self.c.step(row)
        attempts = self.c.store.attempts(row["id"])
        saved = self.c.store.get(row["id"]); saved["state"] = "INTERVENTION"
        self.c.store.save(saved, 22)
        self.c.store.prepare_external_percentage_adoption(row["id"], entry_order_id=42,
            stop_order_id=43, trailing_order_id=99, percent="8.35", now_ms=23)
        self.assertEqual(self.c.step(row, 24)["state"], "PROTECTING")
        self.assertEqual([a["id"] for a in self.c.store.attempts(row["id"])], [a["id"] for a in attempts])
        self.assertEqual(self.c.step(row, 25)["state"], "PROTECTED")
        self.c.g.trading.place_trailing_stop_order.assert_not_called()

    def test_expired_entry_authority_does_not_prevent_read_only_migration(self):
        row = self.queue(); self.c.step(row)
        saved = self.c.store.get(row["id"]); saved["state"] = "INTERVENTION"
        saved["plan"]["expires_ms"] = 21
        self.c.store.save(saved, 22)
        self.c.store.prepare_external_percentage_adoption(row["id"], entry_order_id=42,
            stop_order_id=43, trailing_order_id=99, percent="8.35", now_ms=23,
            admission_expires_ms=30)
        self.assertEqual(self.c.step(row, 24)["state"], "PROTECTING")
        self.assertEqual(self.c.store.get(row["id"])["plan"]["expires_ms"], 21)
        self.c.g.trading.place_order.assert_not_called()

    def test_cancel_pending_migration_never_releases_existing_owner(self):
        row = self.queue(); self.c.step(row)
        saved = self.c.store.get(row["id"]); saved["state"] = "INTERVENTION"
        self.c.store.save(saved, 22)
        self.c.store.prepare_external_percentage_adoption(row["id"], entry_order_id=42,
            stop_order_id=43, trailing_order_id=99, percent="8.35", now_ms=23)
        self.c.store.request_exit(row["id"], 24, cancel_only=True)
        self.assertEqual(self.c.step(row, 25)["state"], "INTERVENTION")
        self.c.g.trading.cancel_order.assert_not_called()

    def test_conflicting_fill_semantics_fail_without_import(self):
        self.c.fills.append(dict(self.c.fills[0], sz="0.5"))
        row = self.queue()
        self.assertEqual(self.c.step(row)["state"], "INTERVENTION")
        self.assertEqual(self.c.store.attempts(row["id"]), [])

    def test_eth_and_sp500_account_size_semantics_preserve_exact_ids(self):
        from decimal import Decimal
        from types import SimpleNamespace
        from unittest.mock import Mock
        from kis_hl.instruments import instrument
        from tests.test_managed_execution import plan
        for key, coin, qty, entry, stop in (("hl:ETH", "ETH", "0.1807", "3000", "2685"),
                                          ("hl:xyz:SP500", "xyz:SP500", "0.1", "6800", "6300")):
            with self.subTest(instrument=key):
                c = test_manual_adoption.ManualAdoptionTests(); c.setUp(); self.addCleanup(c.doCleanups)
                asset = instrument(key)
                c.g._market = Mock(return_value=(asset, SimpleNamespace(coin=coin, dex="xyz" if ":" in coin else None),
                                                Decimal("0.0001"), Decimal("0.1")))
                c.orders[42]["order"].update(coin=coin, origSz=qty, sz="0")
                c.orders[43]["order"].update(coin=coin, sz=qty, triggerPx=stop)
                c.orders[99] = {"status":"open", "order":dict(oid=99, coin=coin, sz=qty, side="A",
                    reduceOnly=True, isTrigger=True, orderType="Trailing Stop Market",
                    triggerCondition=f"retracement 8.35%, best {entry}")}
                c.fills[0].update(coin=coin, sz=qty, px=entry)
                c.info.clearinghouse_state.return_value = {"assetPositions":[{"position":dict(coin=coin, szi=qty, entryPx=entry)}]}
                c.g.preflight.return_value.update(atr_source={"instrument":key}, open_orders=[c.orders[43]["order"],c.orders[99]["order"]])
                p = plan(trailing_provider="native", local_trailing_backup=False, native_trailing_percent="8.35", fixed_stop_price=stop)
                p.update(instrument=key, signal_instrument=key, quantity=qty, limit_price=entry,
                         max_loss="100", max_notional="1000")
                row = c.store.enqueue_adoption(c.g.scope, p,
                    entry_order_id=42, stop_order_id=43, trailing_order_id=99, now_ms=20, live=True)
                self.assertEqual(c.step(row)["state"], "PROTECTING")
                self.assertEqual([a["order_id"] for a in c.store.attempts(row["id"])], ["42","43","99"])
                self.assertEqual(c.store.get(row["id"])["observed_size"], qty)
                c.g.trading.place_order.assert_not_called()
                c.g.trading.place_trailing_stop_order.assert_not_called()

    def test_partial_native_trailing_fill_reconciles_residual_without_full_exit(self):
        row = self.queue(); self.c.step(row)
        self.c.fills.append(dict(self.c.fills[0], tid=2, oid=99, side="A", time=22,
                                 sz="0.5", startPosition="1"))
        self.c.info.clearinghouse_state.return_value["assetPositions"][0]["position"]["szi"] = "0.5"
        self.c.orders[99]["order"]["sz"] = "0.5"
        result = self.c.step(row, 23)
        self.assertEqual(result["state"], "PROTECTED")
        self.assertEqual(result["observed_size"], "0.5")
        self.assertEqual(result["protective_filled"], "0.5")
        self.assertIsNone(result["exit_requested_ms"])
        self.c.g.trading.place_order.assert_not_called()

    def test_bad_exact_evidence_imports_nothing(self):
        for changes in ({"oid": 98}, {"sz": "0.5"}, {"side": "B"},
                        {"triggerCondition": "retracement 8.35%, best waiting"},
                        {"triggerCondition": "retracement 9%, best 105"}):
            with self.subTest(changes=changes):
                self.c.orders[99]["order"].update(changes)
                row = self.queue()
                self.assertEqual(self.c.step(row)["state"], "INTERVENTION")
                self.assertEqual(self.c.store.attempts(row["id"]), [])
                self.c.g.trading.place_order.assert_not_called()
                self.c.g.trading.place_trailing_stop_order.assert_not_called()
                saved = self.c.store.get(row["id"]); saved["state"] = "REJECTED"
                self.c.store.save(saved, 22)
                self.c.orders[99]["order"] = dict(oid=99, coin="BTC", side="A", reduceOnly=True,
                    isTrigger=True, sz="1", orderType="Trailing Stop Market",
                    triggerCondition="retracement 8.35%, best 105")
                self.c.g.preflight.return_value["open_orders"][-1] = self.c.orders[99]["order"]
                # New authority must have a distinct intent.
                with self.c.store.connect() as db:
                    db.execute("DELETE FROM managed_intents")


if __name__ == "__main__":
    unittest.main()
