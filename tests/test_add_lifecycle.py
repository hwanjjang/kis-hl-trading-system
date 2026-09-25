"""Order cancellation budgets and terminal unsent-add retirement."""
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from kis_hl.managed_execution import ExecutionStore, Supervisor
from kis_hl.strategy_signals import Signals
from tests import test_conditional_add as fixtures
from tests.test_conditional_add import (
    AddGateway, add_plan, add_signal, NOW, DAY,
)


class AddLifecycleTests(unittest.TestCase):
    setUp = fixtures.ConditionalAddTests.setUp
    authorize = fixtures.ConditionalAddTests.authorize

    def reopen(self):
        self.store = ExecutionStore(self.store.path)
        self.worker = Supervisor(self.store, self.g, live=True)

    def cancels(self, target):
        return [a for a in self.store.attempts(self.row["id"])
                if a["kind"] == "cancel" and a.get("target_id") == target]

    def historical_entry_cancel(self):
        """Real partial-entry cancellation, followed by a fresh add approval."""
        self.store = ExecutionStore(Path(self.tmp.name)/"historical.sqlite")
        self.g = AddGateway()
        opened = NOW-3*DAY
        p = {**self.row["plan"], "quantity": "2", "expires_ms": opened+1000}
        self.row = self.store.enqueue("scope", p, live=True, now_ms=opened-1000)
        self.worker = Supervisor(self.store, self.g, live=True)
        self.worker.step(self.row["id"], opened)
        original = self.g.sent[0]
        self.g.fill(original, "1", terminal=False)
        for tick in (1, 2, 1001, 1002): self.worker.step(self.row["id"], opened+tick)
        self.row = self.store.get(self.row["id"])
        self.assertEqual(self.row["state"], "PROTECTED")
        self.assertEqual(self.g.orders[original["id"]]["status"], "canceled")
        # Legacy owners retain this field after their original cancellation cycle.
        self.row["cancel_started_ms"] = opened+1001
        self.store.save(self.row, opened+1002)
        self.signals = Signals(self.store)
        add_signal(self.signals, self.row)
        self.plan = add_plan(self.row)

    def send_add(self):
        self.authorize()
        self.worker.step(self.row["id"], NOW+10)
        return next(a for a in self.g.sent if a["kind"] == "add")

    def test_new_add_gets_own_cancel_budget_after_historical_entry_cancel(self):
        self.historical_entry_cancel()
        add = self.send_add()
        old_stop = next(a for a in self.g.sent if a["kind"] == "stop")
        self.reopen()
        expiry = self.plan["expires_ms"]
        self.worker.step(self.row["id"], expiry)
        self.assertEqual(len(self.cancels(add["id"])), 1)
        self.assertEqual(self.g.orders[add["id"]]["status"], "canceled")
        attempt = next(a for a in self.store.attempts(self.row["id"]) if a["id"] == add["id"])
        self.assertEqual(attempt["cancel_started_ms"], expiry)
        self.worker.step(self.row["id"], expiry+1)
        self.assertEqual(self.store.get(self.row["id"])["state"], "PROTECTED")
        self.assertEqual(self.g.orders[old_stop["id"]]["status"], "open")
        self.assertEqual(self.store.tranches(self.row["id"])[0]["status"], "CANCELED")

    def test_same_target_deadline_survives_reopen_and_does_not_reset(self):
        add = self.send_add()
        self.g.cancel = lambda *args: {"status": "rejected"}
        expiry, budget = self.plan["expires_ms"], self.plan["exit_deadline_ms"]
        self.worker.step(self.row["id"], expiry)
        self.reopen()
        self.worker.step(self.row["id"], expiry+budget)
        self.assertEqual(len(self.cancels(add["id"])), 2)
        self.reopen()
        self.worker.step(self.row["id"], expiry+budget+1)
        self.assertEqual(len(self.cancels(add["id"])), 2)
        self.assertEqual(self.store.get(self.row["id"])["state"], "INTERVENTION")

    def test_legacy_same_target_cancel_history_keeps_original_deadline(self):
        add = self.send_add()
        self.g.cancel = lambda *args: {"status": "rejected"}
        expiry, budget = self.plan["expires_ms"], self.plan["exit_deadline_ms"]
        self.worker.step(self.row["id"], expiry+10)
        attempt = next(a for a in self.store.attempts(self.row["id"]) if a["id"] == add["id"])
        attempt.pop("cancel_started_ms", None)
        self.store.update_attempt(attempt)
        owner = self.store.get(self.row["id"])
        owner["cancel_started_ms"] = expiry
        self.store.save(owner, expiry+10)
        self.reopen()
        self.worker.step(self.row["id"], expiry+budget+1)
        self.assertEqual(len(self.cancels(add["id"])), 1)
        self.assertEqual(self.store.get(self.row["id"])["state"], "INTERVENTION")
        restored = next(a for a in self.store.attempts(self.row["id"]) if a["id"] == add["id"])
        self.assertEqual(restored["cancel_started_ms"], expiry)

    def test_legacy_owner_clock_is_used_only_inside_matching_target_interval(self):
        for legacy_kind in ("creation", "before_creation", "first_cancel", "after_cancel", "missing"):
            with self.subTest(legacy_kind=legacy_kind):
                case = AddLifecycleTests()
                case.setUp()
                try:
                    add = case.send_add()
                    case.g.cancel = lambda *args: {"status": "rejected"}
                    first_cancel = case.plan["expires_ms"]
                    case.worker.step(case.row["id"], first_cancel)
                    attempt = next(a for a in case.store.attempts(case.row["id"]) if a["id"] == add["id"])
                    attempt.pop("cancel_started_ms", None)
                    case.store.update_attempt(attempt)
                    owner = case.store.get(case.row["id"])
                    values = {"creation": add["created_ms"], "before_creation": add["created_ms"]-1,
                              "first_cancel": first_cancel, "after_cancel": first_cancel+1, "missing": None}
                    owner["cancel_started_ms"] = values[legacy_kind]
                    case.store.save(owner, first_cancel)
                    case.reopen()
                    case.worker.step(case.row["id"], first_cancel+2)
                    restored = next(a for a in case.store.attempts(case.row["id"]) if a["id"] == add["id"])
                    expected = add["created_ms"] if legacy_kind == "creation" else first_cancel
                    self.assertEqual(restored["cancel_started_ms"], expected)
                finally:
                    case.doCleanups()

    def test_cancel_clock_is_durable_before_process_death_and_unknown_is_not_retried(self):
        add = self.send_add()
        def crash(*args):
            raise KeyboardInterrupt()
        self.g.cancel = crash
        expiry = self.plan["expires_ms"]
        with self.assertRaises(KeyboardInterrupt): self.worker.step(self.row["id"], expiry)
        self.reopen()
        attempt = next(a for a in self.store.attempts(self.row["id"]) if a["id"] == add["id"])
        self.assertEqual(attempt["cancel_started_ms"], expiry)
        self.worker.step(self.row["id"], expiry+1)
        self.assertEqual(len(self.cancels(add["id"])), 1)
        self.assertEqual(self.cancels(add["id"])[0]["status"], "UNKNOWN")
        self.worker.step(self.row["id"], expiry+self.plan["exit_deadline_ms"]+1)
        self.assertEqual(self.store.get(self.row["id"])["state"], "INTERVENTION")
        self.assertEqual(len(self.cancels(add["id"])), 1)

    def test_unknown_add_target_records_cancel_budget_without_sending(self):
        self.authorize()
        original = self.g.submit
        def unknown(owner, attempt):
            if attempt["kind"] == "add":
                self.g.sent.append(dict(attempt))
                raise TimeoutError("Stub acknowledgement lost")
            return original(owner, attempt)
        self.g.submit = unknown
        self.worker.step(self.row["id"], NOW+10)
        expiry = self.plan["expires_ms"]
        self.reopen()
        self.worker.step(self.row["id"], expiry)
        add = next(a for a in self.store.attempts(self.row["id"]) if a["kind"] == "add")
        self.assertEqual(add["cancel_started_ms"], expiry)
        self.assertEqual(add["status"], "UNKNOWN")
        self.assertEqual(self.store.tranches(self.row["id"])[0]["status"], "UNKNOWN")
        self.assertEqual(self.store.get(self.row["id"])["state"], "INTERVENTION")
        self.assertFalse(any(a["kind"] == "cancel" for a in self.store.attempts(self.row["id"])))
        self.assertEqual(sum(a["kind"] == "add" for a in self.g.sent), 1)

    def test_partial_fill_while_cancel_pending_extends_existing_sl(self):
        self.historical_entry_cancel()
        add = self.send_add()
        self.g.cancel = lambda *args: {"status": "submitted"}  # Ack is not terminal evidence.
        expiry = self.plan["expires_ms"]
        self.worker.step(self.row["id"], expiry)
        self.assertEqual(len(self.cancels(add["id"])), 1)
        self.g.fill(add, "0.2", terminal=False)
        self.reopen()
        for tick in (1, 2): self.worker.step(self.row["id"], expiry+tick)
        owner = self.store.get(self.row["id"])
        self.assertEqual(Decimal(owner["covered_size"]), Decimal("1.2"))
        self.assertEqual(len(self.cancels(add["id"])), 1)
        self.g.orders[add["id"]]["status"] = "canceled"
        self.worker.step(self.row["id"], expiry+3)
        self.assertEqual(self.store.get(self.row["id"])["state"], "PROTECTED")
        self.assertEqual(Decimal(self.store.tranches(self.row["id"])[0]["filled"]), Decimal("0.2"))

    def close_owner(self):
        self.store.request_exit(self.row["id"], NOW+6)
        self.worker.step(self.row["id"], NOW+10)
        attempt = next(a for a in self.g.sent if a["kind"] == "exit")
        self.g.size = "0"
        self.g.orders[attempt["id"]].update(status="filled", size="0")
        for tick in (11, 12, 13): self.worker.step(self.row["id"], NOW+tick)
        self.assertEqual(self.store.get(self.row["id"])["state"], "CLOSED")

    def test_full_exit_retires_unsent_add_without_erasing_evidence(self):
        queued = self.authorize()
        self.close_owner()
        retired = self.store.tranches(self.row["id"])[0]
        self.assertEqual(retired["status"], "CANCELED")
        self.assertIn("CLOSED", retired["reason"])
        self.assertEqual(retired["plan"], queued["plan"])
        self.assertEqual(retired["sizing"], queued["sizing"])
        self.assertFalse(any(a["kind"] == "add" for a in self.g.sent))
        self.reopen()
        self.worker.step(self.row["id"], NOW+14)
        self.assertEqual(self.store.tranches(self.row["id"])[0], retired)

    def test_finished_owner_reopen_repairs_legacy_queued_tranche(self):
        queued = self.authorize()
        self.close_owner()
        self.store.save_tranche(queued)  # Legacy CLOSED snapshot with stale QUEUED tranche.
        self.reopen()
        self.worker.step(self.row["id"], NOW+14)
        repaired = self.store.tranches(self.row["id"])[0]
        self.assertEqual(repaired["status"], "CANCELED")
        self.assertEqual(repaired["retired_ms"], NOW+14)
        self.assertFalse(any(a["kind"] == "add" for a in self.store.attempts(self.row["id"])))

    def test_terminal_retirement_never_hides_a_durable_attempt(self):
        queued = self.authorize()
        self.close_owner()
        self.store.save_tranche(queued)
        attempt = self.store.attempt(self.store.get(self.row["id"]), "add", NOW+13,
                                     tranche_id=queued["id"], quantity="0.5", price="100")
        self.reopen()
        self.worker.step(self.row["id"], NOW+14)
        self.assertEqual(self.store.tranches(self.row["id"])[0], queued)
        self.assertEqual(self.store.attempts(self.row["id"])[-1], attempt)
        self.assertEqual(attempt["status"], "UNKNOWN")
        self.assertFalse(any(a["kind"] == "add" for a in self.g.sent))

    def test_terminal_save_and_retirement_commit_or_roll_back_together(self):
        self.authorize()
        with self.store.connect() as db:
            db.execute("CREATE TRIGGER block_retire BEFORE UPDATE ON managed_tranches "
                       "BEGIN SELECT RAISE(ABORT, 'retirement blocked'); END")
        owner = self.store.get(self.row["id"])
        owner["state"] = "CLOSED"
        with self.assertRaises(sqlite3.Error):
            self.store.save(owner, NOW+6)
        self.assertEqual(self.store.get(self.row["id"])["state"], "PROTECTED")
        self.assertEqual(self.store.tranches(self.row["id"])[0]["status"], "QUEUED")

    def test_finished_owner_without_queued_add_takes_no_retirement_lock(self):
        self.authorize()
        self.close_owner()
        statements = []
        original = ExecutionStore.connect

        @contextmanager
        def traced(store):
            with original(store) as db:
                db.set_trace_callback(statements.append)
                yield db

        with patch.object(ExecutionStore, "connect", traced):
            self.worker.step(self.row["id"], NOW+20)
        self.assertFalse([s for s in statements if "BEGIN IMMEDIATE" in s or "managed_attempts" in s])

    def test_expired_unsent_add_retires_while_owner_is_not_protected(self):
        queued = self.authorize()
        owner = self.store.get(self.row["id"])
        owner["state"] = "INTERVENTION"
        self.store.save(owner, NOW+6)
        self.worker.step(self.row["id"], NOW+10)
        self.assertEqual(self.store.tranches(self.row["id"])[0]["status"], "QUEUED")
        expiry = queued["plan"]["expires_ms"]
        self.worker.step(self.row["id"], expiry)
        expired = self.store.tranches(self.row["id"])[0]
        self.assertEqual(expired["status"], "EXPIRED")
        self.assertEqual(expired["retired_ms"], expiry)
        self.assertEqual(expired["sizing"], queued["sizing"])
        self.assertFalse(any(a["kind"] == "add" for a in self.g.sent))

    def test_expiry_retirement_never_hides_a_durable_attempt(self):
        queued = self.authorize()
        owner = self.store.get(self.row["id"])
        owner["state"] = "INTERVENTION"
        self.store.save(owner, NOW+6)
        self.store.attempt(owner, "add", NOW+7, tranche_id=queued["id"], quantity="0.5", price="100")
        self.worker.step(self.row["id"], queued["plan"]["expires_ms"])
        kept = self.store.tranches(self.row["id"])[0]
        self.assertNotEqual(kept["status"], "EXPIRED")
        self.assertNotIn("retired_ms", kept)
        self.assertFalse(any(a["kind"] == "add" for a in self.g.sent))

    def test_all_finished_states_retire_only_unsent_queued_tranches(self):
        for state in ("CLOSED", "REJECTED", "PREVIEWED"):
            with self.subTest(state=state):
                case = AddLifecycleTests()
                case.setUp()
                try:
                    queued = case.authorize()
                    owner = case.store.get(case.row["id"])
                    owner["state"] = state
                    case.store.save(owner, NOW+6)
                    self.assertEqual(case.store.tranches(owner["id"])[0]["status"], "CANCELED")
                    # Legacy cleanup does not infer absence of transmission from a missing attempt.
                    for status in ("UNKNOWN", "SUBMITTED", "FILLED", "CANCELED", "REJECTED", "EXPIRED"):
                        recorded = {**queued, "status": status}
                        case.store.save_tranche(recorded)
                        case.worker.step(owner["id"], NOW+7)
                        self.assertEqual(case.store.tranches(owner["id"])[0], recorded)
                    self.assertFalse(any(a["kind"] == "add" for a in case.g.sent))
                finally:
                    case.doCleanups()


if __name__ == "__main__":
    unittest.main()
