"""Issue 59: account-read outages warn but never liquidate (offline fakes only)."""
import io
import json
import tempfile
import unittest
import urllib.error
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

from kis_hl.config import HyperliquidConfig
from kis_hl.hyperliquid.client import HyperliquidInfoClient, TransientInfoError
import sqlite3

from kis_hl import managed_execution
from kis_hl.managed_execution import ExecutionStore, Supervisor
from tests.read_errors import read_unavailable
from tests.test_kis_adoption import NOW, FixtureKisGateway, plan as kis_plan
from tests.test_managed_execution import Gateway, plan

GRACE, DEADLINE = 5000, 60000
original_connect = sqlite3.connect  # protection_grace_ms / exit_deadline_ms in plan()


def outage(secret="SECRET-TOKEN", status=429):
    exc = TransientInfoError(f"Hyperliquid info temporarily unavailable: HTTP {status} token={secret}")
    exc.kind, exc.http_status = "http", status
    return exc


def owner_diagnostics(store, row, now_ms):
    return managed_execution.owner_diagnostics(store, row, now_ms)


class HyperliquidOwnerBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = ExecutionStore(Path(tmp.name) / "t.sqlite")
        self.g = Gateway()
        self.worker = Supervisor(self.store, self.g, live=True)
        self.healthy = self.g.snapshot

    def protect(self):
        row = self.store.enqueue("scope", plan(), live=True, now_ms=1)
        self.worker.step(row["id"], 10)
        self.g.size = self.g.filled = "1"
        self.g.orders[self.g.sent[0]["id"]]["status"] = "filled"
        self.worker.step(row["id"], 20)
        self.assertEqual(self.worker.step(row["id"], 30)["state"], "PROTECTED")
        self.assertEqual([a["kind"] for a in self.g.sent], ["entry", "stop"])
        return row["id"]

    def fail_reads(self, exc=None):
        self.g.snapshot = Mock(side_effect=exc or outage())

    def recover(self, **changes):
        self.g.snapshot = lambda *a: self.healthy(*a) | changes

    def assert_no_exit(self, result):
        self.assertIsNone(result["exit_requested_ms"])
        self.assertNotIn("read_failure_exit", result)
        self.assertEqual([a["kind"] for a in self.g.sent], ["entry", "stop"])


class HyperliquidReadOutageTests(HyperliquidOwnerBase):
    def test_prolonged_outage_with_restart_never_requests_exit_and_resumes(self):
        pid = self.protect()
        self.fail_reads()
        for now in (40, 50, 60):
            result = self.worker.step(pid, now)
            self.assertEqual(result["state"], "DEGRADED")
            self.assert_no_exit(result)
        self.assertIn("warning only", result["reason"])
        self.worker = Supervisor(ExecutionStore(self.store.path), self.g, live=True)
        for now in (60 + GRACE, 60 + GRACE + DEADLINE + 1, 200_000):
            result = self.worker.step(pid, now)
            self.assertEqual(result["state"], "DEGRADED")
            self.assert_no_exit(result)
        self.assertEqual(result["read_failures"], 6)
        self.recover()
        result = self.worker.step(pid, 200_010)
        self.assertEqual(result["state"], "PROTECTED")
        self.assert_no_exit(result)
        self.assertEqual(result["read_failures"], 0)
        self.assertEqual(result["read_health"]["status"], "ok")
        self.assertEqual(result["read_health"]["last_outage"]["failures"], 6)

    def test_outage_preserves_explicit_exit_and_its_original_budget(self):
        pid = self.protect()
        self.store.request_exit(pid, 35)
        self.fail_reads()
        for now in (40, 50, 60, 70):
            self.assertEqual(self.worker.step(pid, now)["exit_requested_ms"], 35)
        self.recover()
        result = self.worker.step(pid, 1_000)
        self.assertEqual(result["exit_requested_ms"], 35)
        self.assertEqual(self.g.sent[-1]["kind"], "exit")
        self.assertEqual(owner_diagnostics(self.store, result, 1_000)["exit"]["provenance"]["kind"], "operator")

    def test_real_trailing_breach_after_outage_still_exits(self):
        pid = self.protect()
        self.fail_reads()
        for now in (40, 50, 60):
            self.worker.step(pid, now)
        self.recover(price="95")
        self.worker.step(pid, 70)
        self.assertEqual(self.g.sent[-1]["kind"], "exit")

    def test_outage_notifications_are_deduplicated_across_polls_and_restart(self):
        pid = self.protect()
        self.fail_reads()
        for now in (40, 50, 60):
            self.worker.step(pid, now)
        self.worker = Supervisor(ExecutionStore(self.store.path), self.g, live=True)
        for now in (70, 80):
            self.worker.step(pid, now)
        pending = self.store.notifications("scope", "live")
        self.assertEqual([n["kind"] for n in pending], ["read_outage"])
        warning = pending[0]
        self.assertEqual(warning["episode_ms"], 40)
        self.assertEqual(warning["payload"]["instrument"], "hl:BTC")
        self.assertEqual(warning["payload"]["read_health"]["error"],
                         {"category": "TransientInfoError", "kind": "http", "http_status": 429})
        self.assertEqual(warning["payload"]["local_supervision"], "paused")
        self.assertEqual(warning["payload"]["native_orders_retained"], [self.g.sent[1]["id"]])
        self.assertIn("no exit requested", warning["message"])
        self.recover()
        for now in (90, 100, 110):
            self.worker.step(pid, now)
        pending = self.store.notifications("scope", "live")
        self.assertEqual([n["kind"] for n in pending], ["read_outage", "read_recovered"])
        self.assertEqual(pending[1]["episode_ms"], 40)
        self.assertEqual(pending[1]["payload"]["read_health"]["last_outage"]["failures"], 5)
        self.assertNotIn("SECRET", json.dumps(pending))

    def test_failed_delivery_stays_pending_and_never_affects_execution(self):
        pid = self.protect()
        self.fail_reads()
        self.worker.step(pid, 40)
        before = self.store.get(pid)
        note = self.store.notifications("scope", "live")[0]
        self.store.record_notification_result(note["id"], delivered=False, now_ms=45)
        self.store.record_notification_result(note["id"], delivered=False, now_ms=46)
        retry = self.store.notifications("scope", "live")
        self.assertEqual(len(retry), 1)
        self.assertEqual((retry[0]["delivery_attempts"], retry[0]["last_attempt_ms"]), (2, 46))
        self.assertEqual(self.store.get(pid), before)
        self.store.record_notification_result(note["id"], delivered=True, now_ms=47)
        self.assertEqual(self.store.notifications("scope", "live"), [])
        with self.assertRaises(ValueError):
            self.store.record_notification_result(note["id"], delivered=True, now_ms=48)
        self.assertEqual(self.store.get(pid), before)
        self.assertEqual([a["kind"] for a in self.g.sent], ["entry", "stop"])

    def test_read_health_classification_is_structured_and_secret_free(self):
        pid = self.protect()
        cases = ((outage(), {"category": "TransientInfoError", "kind": "http", "http_status": 429}),
                 (TimeoutError("password=SECRET"), {"category": "TimeoutError", "kind": "timeout", "http_status": None}),
                 (read_unavailable("KIS account inquiry failed SECRET"), {"category": "RuntimeError", "kind": "other", "http_status": None}))
        for now, (exc, expected) in zip((40, 50, 60), cases):
            self.fail_reads(exc)
            result = self.worker.step(pid, now)
            self.assertEqual(result["read_health"]["error"], expected)
            self.assertEqual(result["read_health"]["operation"], "account_snapshot")
        with self.store.connect() as db:
            events = [tuple(r) for r in db.execute("SELECT reason, details FROM managed_events")]
        self.assertNotIn("SECRET", json.dumps([result, events, self.store.notifications("scope", "live")]))

    def test_malformed_read_evidence_stays_fail_closed(self):
        # R1-F3: a successful response with invalid evidence is not an outage.
        pid = self.protect()
        self.fail_reads(RuntimeError("Hyperliquid orderStatus returned an unexpected response"))
        result = self.worker.step(pid, 40)
        self.assertEqual(result["state"], "INTERVENTION")
        self.assertEqual(result["read_health"]["status"], "ok")  # evidence failure, not an outage
        self.recover()
        self.assertEqual(self.worker.step(pid, 50)["state"], "INTERVENTION")
        self.assertEqual(self.store.notifications("scope", "live"), [])
        self.assertEqual([a["kind"] for a in self.g.sent], ["entry", "stop"])

    def test_later_read_failure_does_not_hide_current_deadline_blocker(self):
        pid = self.protect()
        self.recover(consistent=False)
        first = self.worker.step(pid, 40)
        self.assertEqual(first["first_intervention"]["reason"], "External ownership or inconsistent exposure")
        self.recover()
        self.store.recover_intervention(pid, 45)
        self.store.request_exit(pid, 50)
        self.fail_reads()
        for now in (60, 70, 80):
            self.worker.step(pid, now)
        self.recover()
        blocked = self.worker.step(pid, 50 + DEADLINE + 10)
        self.assertEqual(blocked["state"], "INTERVENTION")
        self.assertEqual(blocked["reason"], "Exit attempt or deadline budget exhausted")
        self.fail_reads()
        later = self.worker.step(pid, 50 + DEADLINE + 20)
        self.assertEqual(later["reason"], "Exit attempt or deadline budget exhausted")
        self.assertEqual(later["read_health"]["status"], "unavailable")
        self.recover()
        result = self.worker.step(pid, 50 + DEADLINE + 30)
        self.assertEqual(result["reason"], "Exit attempt or deadline budget exhausted")
        self.assertEqual(result["intervention_blocker"]["reason"], "Exit attempt or deadline budget exhausted")
        self.assertEqual(result["first_intervention"], first["first_intervention"])
        diag = owner_diagnostics(self.store, result, 50 + DEADLINE + 30)
        self.assertEqual(diag["intervention"]["first_cause"]["reason"], "External ownership or inconsistent exposure")
        self.assertEqual(diag["intervention"]["current_blocker"]["reason"], "Exit attempt or deadline budget exhausted")
        self.assertTrue(diag["exit"]["deadline_exhausted"])
        self.assertEqual(diag["exit"]["exit_attempts"], 0)
        self.assertEqual(diag["supervision"]["local_supervision"], "paused")
        self.assertEqual(diag["supervision"]["native_orders_retained"], [self.g.sent[1]["id"]])
        self.assertEqual(diag["read_health"]["status"], "ok")
        events = diag["events"]
        self.assertGreater(events["polls"], 0)
        self.assertEqual(events["total"], events["polls"] + events["transition_count"])
        self.assertEqual([t["reason"] for t in events["recent_transitions"]
                          if t["state"] == "INTERVENTION"][-1], "Exit attempt or deadline budget exhausted")
        self.assertEqual([a["kind"] for a in self.g.sent], ["entry", "stop"])


class LegacyLatchTests(HyperliquidOwnerBase):
    """Rows latched by the pre-issue-59 read-outage policy."""

    OUTAGE = "Account snapshot unavailable (TransientInfoError); consecutive failures=3; awaiting readback"

    def latch(self, pid, at, *, flag, event_ms=None):
        row = self.store.get(pid)
        row.update(exit_requested_ms=at, state="INTERVENTION", reason=self.OUTAGE)
        if flag:
            row["read_failure_exit"] = True
        self.store.save(row, at if event_ms is None else event_ms)
        return row

    def test_pending_legacy_flag_blocks_without_exit_on_recovery(self):
        pid = self.protect()
        self.latch(pid, 40, flag=True)
        result = self.worker.step(pid, 50)
        self.assertEqual(result["state"], "INTERVENTION")
        self.assertIn("Legacy read-outage exit latch", result["reason"])
        self.assertTrue(result["read_failure_exit"])
        self.assertEqual(result["exit_requested_ms"], 40)
        self.assertEqual([a["kind"] for a in self.g.sent], ["entry", "stop"])
        with self.assertRaisesRegex(ValueError, "withdraw-read-exit"):
            self.store.recover_intervention(pid, 60)

    def test_recover_explains_exhausted_deadline_and_provenance(self):
        pid = self.protect()
        self.latch(pid, 40, flag=False)
        row = self.store.get(pid)
        row["state"] = "EXITING"
        self.store.save(row, 50)
        result = self.worker.step(pid, 40 + DEADLINE + 1)
        self.assertEqual(result["reason"], "Exit attempt or deadline budget exhausted")
        diag = owner_diagnostics(self.store, result, 40 + DEADLINE + 2)
        self.assertEqual(diag["exit"]["provenance"]["kind"], "read_outage_latch")
        self.assertEqual(diag["exit"]["provenance"]["evidence"], "event")
        with self.assertRaises(ValueError) as raised:
            self.store.recover_intervention(pid, 40 + DEADLINE + 2)
        message = str(raised.exception)
        self.assertIn("deadline", message)
        self.assertIn("read_outage_latch", message)
        self.assertIn("withdraw-read-exit --id " + pid + " --exit-requested-ms 40", message)
        self.assertEqual(self.store.get(pid)["state"], "INTERVENTION")

    def test_exact_scoped_withdrawal_then_explicit_recovery_resumes_protection(self):
        pid = self.protect()
        self.latch(pid, 40, flag=False)
        self.worker.step(pid, 40 + DEADLINE + 1)
        with self.assertRaisesRegex(ValueError, "exact"):
            self.store.withdraw_read_outage_exit(pid, 41, now_ms=DEADLINE + 100)
        row = self.store.withdraw_read_outage_exit(pid, 40, now_ms=DEADLINE + 100)
        self.assertEqual(row["state"], "INTERVENTION")
        self.assertIsNone(row["exit_requested_ms"])
        self.assertEqual(row["withdrawn_exit_requests"][0]["exit_requested_ms"], 40)
        self.assertEqual(row["withdrawn_exit_requests"][0]["provenance"]["kind"], "read_outage_latch")
        with self.assertRaises(ValueError):
            self.store.withdraw_read_outage_exit(pid, 40, now_ms=DEADLINE + 101)
        self.store.recover_intervention(pid, DEADLINE + 110)
        result = self.worker.step(pid, DEADLINE + 120)
        self.assertEqual(result["state"], "PROTECTED")
        self.assertEqual([a["kind"] for a in self.g.sent], ["entry", "stop"])

    def test_flag_on_preexisting_operator_exit_is_ambiguous_and_honored(self):
        # R1-F2: the old code set the flag on top of an earlier independent request.
        pid = self.protect()
        row = self.store.get(pid)
        row["exit_requested_ms"] = 35  # pre-issue-59 request_exit recorded no source
        self.store.save(row, 35)
        row = self.store.get(pid)
        row.update(state="DEGRADED", reason="Account snapshot unavailable (OSError); consecutive failures=2; awaiting readback")
        self.store.save(row, 50)
        self.latch(pid, 35, flag=True, event_ms=60)
        diag = owner_diagnostics(self.store, self.store.get(pid), 70)
        self.assertEqual(diag["exit"]["provenance"]["kind"], "ambiguous_legacy")
        with self.assertRaisesRegex(ValueError, "ambiguous_legacy"):
            self.store.withdraw_read_outage_exit(pid, 35, now_ms=70)
        result = self.worker.step(pid, 80)
        self.assertNotIn("read_failure_exit", result)
        self.assertEqual(result["exit_requested_ms"], 35)
        self.assertEqual(self.g.sent[-1]["kind"], "exit")

    def test_outage_event_inside_existing_intervention_is_not_a_latch(self):
        pid = self.protect()
        row = self.store.get(pid)
        row.update(state="INTERVENTION", reason="External ownership or inconsistent exposure")
        self.store.save(row, 40)
        self.latch(pid, 50, flag=False)
        self.assertEqual(owner_diagnostics(self.store, self.store.get(pid), 60)["exit"]["provenance"]["kind"], "other")

    def test_withdrawal_refuses_when_either_protective_fill_counter_is_positive(self):
        # R1-F4: exit_protective_filled=0 must not mask protective_filled>0.
        pid = self.protect()
        row = self.latch(pid, 40, flag=False)
        row = self.store.get(pid)
        row.update(protective_filled="0.1", exit_protective_filled="0")
        self.store.save(row, 41)
        with self.assertRaisesRegex(ValueError, "Protective fills"):
            self.store.withdraw_read_outage_exit(pid, 40, now_ms=50)
        self.assertEqual(self.store.get(pid)["exit_requested_ms"], 40)

    def test_withdrawal_validates_and_writes_atomically_against_reconciliation(self):
        # R1-F5: a stop fill committed between validation reads and the write must win.
        pid = self.protect()
        self.latch(pid, 40, flag=False)
        stop = next(a for a in self.store.attempts(pid) if a["kind"] == "stop")
        other = ExecutionStore(self.store.path)
        original = managed_execution.exit_provenance

        def interleave(store, row, db=None):
            try:
                other.update_attempt(dict(stop), status="FILLED")
            except Exception as exc:  # writer must wait for the withdrawal transaction
                interleave.blocked = type(exc).__name__
            return original(store, row, db=db)
        interleave.blocked = None
        with patch.object(managed_execution, "exit_provenance", interleave), \
                patch("kis_hl.managed_execution.sqlite3.connect",
                      side_effect=lambda path, timeout=10: original_connect(path, timeout=0.05)):
            try:
                self.store.withdraw_read_outage_exit(pid, 40, now_ms=50)
                withdrawn = True
            except ValueError:
                withdrawn = False
        stop_now = next(a for a in self.store.attempts(pid) if a["kind"] == "stop")
        # Either the concurrent fill was serialized after the withdrawal (blocked),
        # or the withdrawal saw it and refused; never both a withdrawal and a hidden fill.
        self.assertFalse(withdrawn and stop_now["status"] == "FILLED")
        self.assertEqual(interleave.blocked, "OperationalError")

    def test_withdrawal_refuses_operator_exit_attempts_and_identity_interventions(self):
        pid = self.protect()
        self.store.request_exit(pid, 40)
        row = self.store.get(pid)
        row.update(state="INTERVENTION", reason="Exit attempt or deadline budget exhausted")
        self.store.save(row, 41)
        with self.assertRaisesRegex(ValueError, "read_outage_latch"):
            self.store.withdraw_read_outage_exit(pid, 40, now_ms=50)
        row = self.store.get(pid)
        row.update(exit_requested_ms=None, state="PROTECTED", reason="Coverage verified; local trailing active")
        self.store.save(row, 52)
        self.latch(pid, 60, flag=True)
        self.store.attempt(self.store.get(pid), "exit", 61, quantity="1", price="99")
        with self.assertRaisesRegex(ValueError, "exit attempt"):
            self.store.withdraw_read_outage_exit(pid, 60, now_ms=70)
        self.assertEqual(self.store.get(pid)["exit_requested_ms"], 60)

    def test_identity_intervention_and_unknown_attempts_stay_fail_closed(self):
        pid = self.protect()
        self.recover(foreign_add=True)
        result = self.worker.step(pid, 40)
        self.assertEqual(result["state"], "INTERVENTION")
        with self.assertRaises(ValueError):
            self.store.withdraw_read_outage_exit(pid, 40, now_ms=50)
        self.fail_reads()
        for now in (60, 70, 80):
            self.assertEqual(self.worker.step(pid, now)["state"], "INTERVENTION")
        self.recover()
        self.assertEqual(self.worker.step(pid, 90)["state"], "INTERVENTION")
        self.assertEqual([a["kind"] for a in self.g.sent], ["entry", "stop"])


class KisReadOutageTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = ExecutionStore(Path(tmp.name) / "t.sqlite")
        self.g = FixtureKisGateway()
        self.worker = Supervisor(self.store, self.g, live=True)
        self.row = self.store.enqueue_adoption(
            self.g.scope, kis_plan(expires_ms=NOW + 600_000), entry_order_id="0017865300",
            stop_order_id=None, live=True, now_ms=NOW, entry_since_ms=NOW - 3_600_000)
        self.step(NOW + 1_000)
        self.assertEqual(self.step(NOW + 2_000)["state"], "PROTECTED")
        self.healthy = self.g.snapshot

    def step(self, at):
        self.g._clock = at
        return self.worker.step(self.row["id"], at)

    def outage_then_recover(self, start, end, *, restart_at=None):
        self.g.snapshot = Mock(side_effect=read_unavailable("KIS account inquiry failed appsecret=SECRET"))
        for at in range(start, end, 5_000):
            if at == restart_at:
                self.worker = Supervisor(ExecutionStore(self.store.path), self.g, live=True)
            result = self.step(at)
            self.assertEqual(result["state"], "DEGRADED")
            self.assertIsNone(result["exit_requested_ms"])
        self.g.snapshot = self.healthy
        return self.step(end)

    def test_in_session_outage_beyond_grace_and_deadline_sends_nothing(self):
        # protection_grace_ms and exit_deadline_ms are both 120000 in the KIS fixture plan.
        result = self.outage_then_recover(NOW + 5_000, NOW + 305_000, restart_at=NOW + 150_000)
        self.assertEqual(result["state"], "PROTECTED")
        self.assertIsNone(result["exit_requested_ms"])
        self.assertNotIn("read_failure_exit", result)
        self.assertEqual(self.g.sent, [])
        kinds = [n["kind"] for n in self.store.notifications(self.g.scope, "live")]
        self.assertEqual(kinds, ["read_outage", "read_recovered"])
        self.assertNotIn("SECRET", json.dumps(self.store.notifications(self.g.scope, "live")))

    def test_real_fixed_stop_breach_after_outage_still_sells(self):
        self.g.quote = (Decimal("102650"), Decimal("102660"))
        self.outage_then_recover(NOW + 5_000, NOW + 305_000)
        self.assertEqual([a["kind"] for a in self.g.sent], ["exit"])

    def slow_failures(self, *starts, completes_after=135_000):
        from kis_hl.managed_gateways import ManagedKisGateway

        def slow(row, attempts, now):
            def history(*args):
                self.g._clock = now + completes_after  # broker read hangs, then fails
                raise read_unavailable("KIS account inquiry failed")
            with patch.object(self.g, "_history", history), \
                    patch("kis_hl.managed_gateways.time.time", side_effect=lambda: self.g._clock / 1000):
                return ManagedKisGateway.snapshot(self.g, row, attempts, now)
        self.g.snapshot = slow
        for at in starts:
            result = self.step(at)
            self.assertEqual(result["state"], "DEGRADED")
            self.assertIsNone(result["exit_requested_ms"])
        self.g.snapshot = self.healthy

    def test_slow_failed_reads_are_not_counted_as_unsupervised_time(self):
        # R1-F1: read latency of failed reads is outage time, never a gap.
        self.slow_failures(NOW + 5_000)
        result = self.step(NOW + 140_001)
        self.assertIsNone(result["exit_requested_ms"])
        self.assertEqual(result["state"], "PROTECTED")
        self.slow_failures(NOW + 145_000, NOW + 280_001, NOW + 415_002)
        self.worker = Supervisor(ExecutionStore(self.store.path), self.g, live=True)
        result = self.step(NOW + 550_003)
        self.assertIsNone(result["exit_requested_ms"])
        self.assertEqual(self.g.sent, [])

    def test_malformed_kis_account_page_stays_fail_closed(self):
        # R1-F3: a malformed page is invalid evidence, never a warning-only outage.
        self.g._history = Mock(side_effect=RuntimeError("Malformed KIS account page"))
        result = self.step(NOW + 5_000)
        self.assertEqual(result["state"], "INTERVENTION")
        self.g._history = Mock(return_value=self.g.history)
        self.assertEqual(self.step(NOW + 10_000)["state"], "INTERVENTION")
        self.assertEqual(self.store.notifications(self.g.scope, "live"), [])
        self.assertEqual(self.g.sent, [])

    def test_process_downtime_before_outage_keeps_observation_gap_policy(self):
        # Supervisor absent for 138 s of open session before reads start failing.
        result = self.outage_then_recover(NOW + 140_000, NOW + 150_000)
        self.assertIsNotNone(result["exit_requested_ms"])


class ReadOutageCliTests(unittest.TestCase):
    def setUp(self):
        import contextlib
        from kis_hl.journal_sync import Scope
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name) / "state.sqlite"
        self.scope = Scope("hyperliquid", "testnet", "0x" + "ab" * 20)
        self.store = ExecutionStore(self.db)
        self.g = Gateway()
        self.g.scope = self.scope.key
        self.worker = Supervisor(self.store, self.g, live=True)
        self.contextlib = contextlib

    def cli(self, *args):
        from kis_hl.cli import main
        out, err = io.StringIO(), io.StringIO()
        with (patch("kis_hl.cli.load_env_file"),
              patch("kis_hl.operations_cli.scope_client", return_value=(self.scope, None)),
              self.contextlib.redirect_stdout(out), self.contextlib.redirect_stderr(err)):
            code = main(["--db", str(self.db), *args])
        return code, (json.loads(out.getvalue()) if out.getvalue() else None), err.getvalue()

    def test_hermes_list_fail_ack_and_recover_withdraw_flow(self):
        row = self.store.enqueue(self.scope.key, plan(), live=True, now_ms=1)
        pid = row["id"]
        self.worker.step(pid, 10)
        self.g.size = self.g.filled = "1"
        self.g.orders[self.g.sent[0]["id"]]["status"] = "filled"
        for now in (20, 30):
            self.worker.step(pid, now)
        healthy, self.g.snapshot = self.g.snapshot, Mock(side_effect=outage())
        for now in (40, 50, 60):
            self.worker.step(pid, now)
        code, listed, _ = self.cli("supervisor", "notifications", "--venue", "hyperliquid")
        self.assertEqual(code, 0)
        [note] = listed["notifications"]
        self.assertEqual(note["kind"], "read_outage")
        self.assertIn("Warning only: no exit requested", note["message"])
        self.assertNotIn(self.scope.account, json.dumps(listed))
        self.assertNotIn("SECRET", json.dumps(listed))
        code, result, _ = self.cli("supervisor", "notification-result", "--venue", "hyperliquid",
                                   "--notification-id", str(note["id"]), "--result", "failed")
        self.assertEqual((code, result["delivery_attempts"], result["delivered_ms"]), (0, 1, None))
        self.assertEqual(len(self.cli("supervisor", "notifications", "--venue", "hyperliquid")[1]
                             ["notifications"]), 1)
        self.cli("supervisor", "notification-result", "--venue", "hyperliquid",
                 "--notification-id", str(note["id"]), "--result", "delivered")
        code, status, _ = self.cli("supervisor", "status", "--venue", "hyperliquid")
        self.assertEqual(status["pending_notifications"], 0)
        diag = status["positions"][0]["diagnostics"]
        self.assertEqual(diag["read_health"]["status"], "unavailable")
        self.assertEqual(diag["supervision"]["local_supervision"], "paused")
        self.assertIsNone(status["positions"][0]["exit_requested_ms"])
        # Legacy latch from the old policy, now past its deadline.
        self.g.snapshot = healthy
        current = self.store.get(pid)
        current.update(exit_requested_ms=70, state="INTERVENTION", reason=LegacyLatchTests.OUTAGE)
        self.store.save(current, 70)
        self.worker.step(pid, 70 + DEADLINE + 1)
        code, _, err = self.cli("order", "recover", "--id", pid)
        self.assertEqual(code, 1)
        self.assertIn(f"withdraw-read-exit --id {pid} --exit-requested-ms 70", err)
        code, status, _ = self.cli("order", "status", "--id", pid)
        self.assertEqual(status["diagnostics"]["exit"]["provenance"]["kind"], "read_outage_latch")
        self.assertEqual(self.cli("order", "withdraw-read-exit", "--id", pid, "--exit-requested-ms", "71")[0], 1)
        code, withdrawn, _ = self.cli("order", "withdraw-read-exit", "--id", pid, "--exit-requested-ms", "70")
        self.assertEqual((code, withdrawn["exit_requested_ms"], withdrawn["state"]), (0, None, "INTERVENTION"))
        code, recovered, _ = self.cli("order", "recover", "--id", pid)
        self.assertEqual((code, recovered["state"]), (0, "ENTERING"))
        self.assertEqual(self.worker.step(pid, 70 + DEADLINE + 100)["state"], "PROTECTED")
        self.assertEqual([a["kind"] for a in self.g.sent], ["entry", "stop"])


class KisClientReadAvailabilityTests(unittest.TestCase):
    def client(self):
        from kis_hl.config import load_kis_config
        from kis_hl.kis.client import KisClient
        env = {"SANDBOX": "false", "KIS_API_KEY": "fake", "KIS_API_SECRET": "fake",
               "KIS_STOCK_ACCOUNT": "1234567801", "KIS_API_ST_KEY": "fake", "KIS_API_ST_SECRET": "fake",
               "KIS_ST_STOCK_ACCOUNT": "1234567801", "KIS_MIN_REQUEST_INTERVAL_MS": "0"}
        return KisClient(load_kis_config(env))

    def raised(self, response):
        client = self.client()
        with patch.object(client, "_request_with_auth", return_value=response), \
                self.assertRaises(RuntimeError) as caught:
            client.account_pages("domestic_balance")
        return caught.exception

    def test_broker_refusal_is_read_unavailable_but_malformed_page_is_not(self):
        from kis_hl.kis.client import KisHttpResponse
        http = self.raised(KisHttpResponse(503, {"msg1": "secret"}, {}))
        self.assertTrue(managed_execution.read_unavailable(http))
        self.assertEqual((http.kind, http.http_status), ("http", 503))
        refusal = self.raised(KisHttpResponse(200, {"rt_cd": "1", "msg1": "secret"}, {}))
        self.assertTrue(managed_execution.read_unavailable(refusal))
        malformed = self.raised(KisHttpResponse(200, {"rt_cd": "0", "output": "not-a-list"}, {"tr_cont": "D"}))
        self.assertFalse(managed_execution.read_unavailable(malformed))


class InfoClientClassificationTests(unittest.TestCase):
    def setUp(self):
        self.client = HyperliquidInfoClient(HyperliquidConfig(
            base_url="https://api.hyperliquid.xyz", account_address="fixture-account",
            private_key="", key_profile="default"))

    def raised(self, error):
        with patch("urllib.request.urlopen", side_effect=error), self.assertRaises(RuntimeError) as caught:
            self.client.post_info({"type": "openOrders"})
        return caught.exception

    def test_transport_errors_carry_safe_structured_classification(self):
        http = urllib.error.HTTPError("https://fixture/info", 429, "busy", {}, io.BytesIO(b"{}"))
        self.assertEqual((self.raised(http).kind, self.raised(http).http_status), ("http", 429))
        permanent = urllib.error.HTTPError("https://fixture/info", 403, "no", {}, io.BytesIO(b'{"x":1}'))
        self.assertEqual(getattr(self.raised(permanent), "http_status", None), 403)
        self.assertEqual(self.raised(TimeoutError()).kind, "timeout")
        self.assertEqual(self.raised(urllib.error.URLError(TimeoutError("timed out"))).kind, "timeout")
        self.assertEqual(self.raised(ConnectionResetError()).kind, "transport")
        self.assertTrue(all(managed_execution.read_unavailable(self.raised(e)) for e in (http, permanent)))

    def test_malformed_successful_response_is_not_read_unavailable(self):
        with patch.object(self.client, "post_info", return_value=[]), self.assertRaises(RuntimeError) as caught:
            self.client.order_status(oid=1)
        self.assertFalse(managed_execution.read_unavailable(caught.exception))


if __name__ == "__main__":
    unittest.main()
