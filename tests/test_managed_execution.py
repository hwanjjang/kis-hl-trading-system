import tempfile
import unittest
from pathlib import Path
from kis_hl.managed_execution import ExecutionStore, Supervisor, validate_plan


def plan(**changes):
    return dict(
        intent_id="fixture-intent",
        instrument="hl:BTC",
        signal_instrument="hl:BTC",
        strategy="fixture",
        strategy_version="1",
        quantity="1",
        limit_price="100",
        atr="2",
        atr_multiple="2",
        max_notional="101",
        max_loss="5",
        max_quote_age_ms=1000,
        protection_grace_ms=5000,
        max_exit_attempts=3,
        exit_deadline_ms=60000,
        slippage="0.01",
        allow_local_sl=True,
        expires_ms=1000000,
        exit_reprice_ms=5000,
        max_portfolio_notional="1000",
        max_correlated_notional="500",
        max_spread_bps="20",
        max_entry_deviation_bps="100",
        **changes,
    )


class Gateway:
    network = "test"
    account = "test-account"
    scope = "scope"
    native_sl = True

    def __init__(self):
        self.sent = []
        self.size = "0"
        self.filled = "0"
        self.orders = {}
        self.foreign = False

    def preflight(self, p, now):
        return {
            "price": "100",
            "ask": "100.1",
            "time_ms": now,
            "available_notional": "1000",
            "position": "0",
            "open_orders": [],
            "eligible": True,
            "session_open": True,
            "quantity_step": "0.01",
            "price_step": "0.01",
            "portfolio_notional": "0",
            "correlated_notional": "0",
            "atr": "2",
            "atr_source": {"instrument": p["instrument"], "basis": "fixture"},
        }

    def snapshot(self, row, attempts, now):
        return {
            "size": self.size,
            "entry_price": "100",
            "entry_filled": self.filled,
            "price": "100",
            "time_ms": now,
            "sellable": self.size,
            "session_open": True,
            "foreign_add": self.foreign,
            "orders": dict(self.orders),
            "consistent": True,
            "price_step": "0.01",
            "quantity_step": "0.01",
        }

    def submit(self, row, attempt):
        self.sent.append(dict(attempt))
        oid = attempt["id"]
        self.orders[oid] = {
            "status": "open",
            "size": attempt["quantity"],
            "kind": attempt["kind"],
            "trigger_price": attempt.get("trigger_price"),
            "side": "sell",
            "reduce_only": True,
            "trigger_type": "sl",
        }
        return {"status": "submitted", "order_id": oid}

    def cancel(self, row, attempt):
        self.orders[attempt["target_id"]]["status"] = "canceled"
        return {"status": "submitted"}


class ManagedExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = ExecutionStore(Path(self.tmp.name) / "test.sqlite")
        self.g = Gateway()
        self.worker = Supervisor(self.store, self.g, live=True)

    def queue(self, p=None):
        return self.store.enqueue("scope", p or plan(), live=True, now_ms=1)

    def test_preview_rejects_missing_risk_and_bad_numbers(self):
        p = plan()
        del p["max_loss"]
        with self.assertRaises(ValueError):
            validate_plan(p, 1)
        p = plan()
        p["quantity"] = "NaN"
        with self.assertRaises(ValueError):
            validate_plan(p, 1)

    def test_one_cycle_per_instrument_and_intent_deduplication(self):
        row = self.queue()
        with self.assertRaisesRegex(RuntimeError, "owned"):
            self.queue()
        self.assertEqual(self.store.get(row["id"])["state"], "QUEUED")

    def test_intent_cannot_be_replayed_after_close(self):
        row = self.queue()
        self.store.request_exit(row["id"], 2, cancel_only=True)
        self.worker.step(row["id"], 10)
        with self.assertRaisesRegex(RuntimeError, "intent"):
            self.queue()

    def test_concentration_spread_and_atr_are_checked_before_entry(self):
        for changes in [
            {"portfolio_notional": "999"},
            {"correlated_notional": "499"},
            {"ask": "110"},
            {"atr": "3"},
        ]:
            with self.subTest(changes=changes):
                p = plan()
                p["intent_id"] = str(changes)
                row = self.queue(p)
                original = self.g.preflight
                self.g.preflight = lambda *a: {**original(*a), **changes}
                self.worker.step(row["id"], 10)
                self.assertEqual(self.g.sent, [])
                current = self.store.get(row["id"])
                current["state"] = "REJECTED"
                self.store.save(current)
                self.g.preflight = original

    def test_partial_fill_receives_actual_native_stop(self):
        row = self.queue()
        self.worker.step(row["id"], 10)
        self.g.size = self.g.filled = "0.4"
        self.worker.step(row["id"], 20)
        self.assertEqual(self.g.sent[-1]["kind"], "stop")
        self.assertEqual(self.g.sent[-1]["quantity"], "0.4")
        self.assertEqual(self.g.sent[-1]["trigger_price"], "96")
        self.assertEqual(self.g.sent[-1]["price"], "95.04")
        self.worker.step(row["id"], 30)
        self.assertEqual(self.store.get(row["id"])["state"], "PROTECTED")

    def test_unknown_entry_is_not_resent(self):
        row = self.queue()

        def unknown(r, a):
            self.g.sent.append(a)
            raise TimeoutError()

        self.g.submit = unknown
        self.worker.step(row["id"], 10)
        self.worker.step(row["id"], 20)
        self.assertEqual(len(self.g.sent), 1)
        self.assertEqual(self.store.attempts(row["id"])[0]["status"], "UNKNOWN")

    def test_unprotected_partial_entry_cancels_remaining_before_exit(self):
        row = self.queue()
        self.worker.step(row["id"], 10)
        self.g.size = self.g.filled = "0.4"
        self.g.native_sl = False
        p = self.store.get(row["id"])
        p["plan"]["allow_local_sl"] = False
        self.store.save(p)
        self.worker.step(row["id"], 20)
        self.worker.step(row["id"], 6000)
        self.assertNotIn("exit", [a["kind"] for a in self.g.sent])
        self.assertEqual(self.store.get(row["id"])["state"], "EXIT_PENDING")
        self.worker.step(row["id"], 6100)
        self.assertEqual(self.g.sent[-1]["kind"], "exit")

    def test_manual_add_stops_automation(self):
        row = self.queue()
        self.worker.step(row["id"], 10)
        self.g.foreign = True
        self.worker.step(row["id"], 20)
        self.assertEqual(self.store.get(row["id"])["state"], "INTERVENTION")

    def test_paper_worker_never_sends(self):
        row = self.store.enqueue("scope", plan(), live=False, now_ms=1)
        Supervisor(self.store, self.g, live=False).step(row["id"], 10)
        self.assertEqual(self.g.sent, [])
        self.assertEqual(self.store.get(row["id"])["state"], "PREVIEWED")

    def test_exposure_limits_checked_again_at_send(self):
        row = self.queue()
        original = self.g.preflight
        self.g.preflight = lambda p, t: {**original(p, t), "available_notional": "10"}
        self.worker.step(row["id"], 10)
        self.assertEqual(self.g.sent, [])
        self.assertEqual(self.store.get(row["id"])["state"], "INTERVENTION")

    def test_kill_switch_changed_during_preflight_blocks_send(self):
        row = self.queue()
        original = self.g.preflight

        def preflight(p, now):
            self.store.set_entries("scope", False)
            return original(p, now)

        self.g.preflight = preflight
        self.worker.step(row["id"], 10)
        self.assertEqual(self.g.sent, [])

    def test_stop_ack_is_not_verified_coverage(self):
        row = self.queue()
        self.worker.step(row["id"], 10)
        self.g.size = self.g.filled = "0.4"
        self.worker.step(row["id"], 20)
        self.assertNotEqual(self.store.get(row["id"])["state"], "PROTECTED")

    def test_queued_cancel_never_sends_entry(self):
        row = self.queue()
        self.store.request_exit(row["id"], 2, cancel_only=True)
        self.worker.step(row["id"], 10)
        self.assertEqual(self.g.sent, [])
        self.assertEqual(self.store.get(row["id"])["state"], "CLOSED")

    def test_restart_before_attempt_rechecks_preflight_and_expiry(self):
        row = self.queue()
        row["state"] = "ENTERING"
        self.store.save(row)
        self.worker.step(row["id"], 1000001)
        self.assertEqual(self.g.sent, [])
        self.assertEqual(self.store.get(row["id"])["state"], "INTERVENTION")

    def test_intervention_flat_cleanup_still_cancels_owned_stop(self):
        row = self.queue()
        self.worker.step(row["id"], 10)
        self.g.size = self.g.filled = "1"
        self.g.orders[self.g.sent[0]["id"]]["status"] = "filled"
        self.worker.step(row["id"], 20)
        self.worker.step(row["id"], 30)
        current = self.store.get(row["id"])
        current["state"] = "INTERVENTION"
        self.store.save(current)
        self.g.size = "0"
        self.worker.step(row["id"], 100)
        self.worker.step(row["id"], 110)
        self.assertEqual(self.store.get(row["id"])["state"], "CLOSED")

    def test_existing_live_owner_blocks_raw_entry(self):
        from kis_hl.managed_execution import guard_external_entry, entry_permit

        row = self.queue()
        with self.assertRaisesRegex(RuntimeError, "blocks"):
            guard_external_entry(self.store.path, scope="scope", instrument_id="hl:BTC")
        with entry_permit("scope", "hl:BTC", "current"):
            guard_external_entry(
                self.store.path,
                scope="scope",
                instrument_id="hl:BTC",
                attempt_id="current",
            )
            with self.assertRaises(RuntimeError):
                guard_external_entry(
                    self.store.path,
                    scope="scope",
                    instrument_id="hl:BTC",
                    attempt_id="other",
                )

    def test_stale_partial_fill_starts_deadline_and_cancels_remainder(self):
        row = self.queue()
        self.worker.step(row["id"], 10)
        self.g.size = self.g.filled = "0.4"
        original = self.g.snapshot
        self.g.snapshot = lambda *a: {**original(*a), "time_ms": 0}
        self.worker.step(row["id"], 2000)
        self.worker.step(row["id"], 8000)
        current = self.store.get(row["id"])
        self.assertIsNotNone(current["first_fill_ms"])
        self.assertIsNotNone(current["exit_requested_ms"])
        self.assertTrue(
            any(a["kind"] == "cancel" for a in self.store.attempts(row["id"]))
        )
        self.assertNotIn("exit", [a["kind"] for a in self.g.sent])

    def test_last_exit_is_reconciled_even_after_budget_exhaustion(self):
        p = plan()
        p["max_exit_attempts"] = 1
        row = self.queue(p)
        self.worker.step(row["id"], 10)
        entry = self.g.sent[0]["id"]
        self.g.orders[entry]["status"] = "filled"
        self.g.size = self.g.filled = "1"
        self.store.request_exit(row["id"], 15)
        self.worker.step(row["id"], 20)
        self.worker.step(row["id"], 30)
        exit_id = self.g.sent[-1]["id"]
        self.assertEqual(self.g.sent[-1]["kind"], "exit")
        self.g.orders[exit_id]["status"] = "filled"
        self.g.size = "0"
        self.worker.step(row["id"], 40)
        self.assertEqual(self.store.get(row["id"])["state"], "CLOSED")

    def test_invalid_native_stop_is_not_coverage(self):
        row = self.queue()
        self.worker.step(row["id"], 10)
        self.g.size = self.g.filled = "0.4"
        self.worker.step(row["id"], 20)
        self.g.orders[self.g.sent[-1]["id"]].update(
            side="buy", reduce_only=False, trigger_type="tp"
        )
        self.worker.step(row["id"], 30)
        self.assertNotEqual(self.store.get(row["id"])["state"], "PROTECTED")

    def test_exit_intent_survives_process_death_during_cancel(self):
        row = self.queue()
        self.worker.step(row["id"], 10)
        self.g.size = self.g.filled = "0.4"
        self.g.native_sl = False
        original = self.g.snapshot
        self.g.snapshot = lambda *a: {**original(*a), "price": "90"}

        def crash(*a):
            raise KeyboardInterrupt()

        self.g.cancel = crash
        with self.assertRaises(KeyboardInterrupt):
            self.worker.step(row["id"], 20)
        self.assertIsNotNone(self.store.get(row["id"])["exit_requested_ms"])

    def test_rejected_cancel_has_bounded_retry(self):
        row = self.queue()
        self.worker.step(row["id"], 10)
        self.store.request_exit(row["id"], 15)
        self.g.cancel = lambda *a: {"status": "rejected"}
        for now in [20, 30, 40, 70000]:
            self.worker.step(row["id"], now)
        attempts = [a for a in self.store.attempts(row["id"]) if a["kind"] == "cancel"]
        self.assertEqual(len(attempts), 3)
        self.assertEqual(self.store.get(row["id"])["state"], "INTERVENTION")


if __name__ == "__main__":
    unittest.main()
