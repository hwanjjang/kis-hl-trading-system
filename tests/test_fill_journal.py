"""Issue #58: fill-triggered journal sync, journal notifications and journal status."""
import contextlib
import io
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from kis_hl import fill_journal
from kis_hl.data_ingestion import ingest_rows
from kis_hl.data_jobs import configure, run_due
from kis_hl.data_store import DataStore
from kis_hl.journal_sync import Scope
from kis_hl.managed_execution import ExecutionStore, Supervisor, notification_message
from tests.test_managed_execution import Gateway, plan

ADDRESS = "0x" + "ab" * 20
HL = Scope("hyperliquid", "mainnet", ADDRESS)
KIS = Scope("kis", "live", "12345678-01")
# 2026-10-13 13:31:05 UTC = 22:31:05 KST.
T0 = 1_791_898_265_000


def hl_fill(tid, before, side="B", size="1", px="10", time=None, pnl="0"):
    return dict(coin="BTC", tid=tid, time=T0 + tid if time is None else time, side=side, sz=size,
                px=px, fee="0.01", feeToken="USDC", oid=tid, startPosition=before, closedPnl=pnl)


class FakeHyperliquid:
    """Read-only info client: user fills within the requested window."""

    def __init__(self):
        self.fills = []
        self.calls = []
        self.fail = None
        self.last_raw_body = None

    def user_fills_by_time(self, *, start_time_ms, end_time_ms):
        self.calls.append(("fills", start_time_ms, end_time_ms))
        if self.fail:
            raise self.fail
        return [f for f in self.fills if start_time_ms <= f["time"] <= end_time_ms]

    def user_funding(self, *, start_time_ms, end_time_ms):
        return []

    def user_fills(self):
        return list(self.fills) or [hl_fill(0, "0", time=0)]

    def clearinghouse_state(self, dex=None):
        return {"assetPositions": []}


def statement(index, side, quantity, price, *, precision="MILLISECOND", before=None, at=None):
    row = dict(source_id=str(index), instrument="kis:005930", currency="KRW",
               event_start_ms=at if at is not None else T0 + index, time_precision=precision,
               grain="EXECUTION", side=side, quantity=str(quantity), price=str(price),
               notional=str(quantity * price), total_cost="1", costs={"broker": "1"})
    row["event_end_ms"] = row["event_start_ms"] + (86_400_000 if precision == "DAY" else 1)
    if before is not None:
        row["position_before"] = str(before)
    return row


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name) / "state.sqlite"
        self.data = DataStore(self.db)
        self.store = ExecutionStore(self.db)
        self.hl = FakeHyperliquid()

    def requests(self):
        return fill_journal.sync_requests(self.db)

    def notes(self, kind=None):
        rows = self.store.notifications(include_delivered=True)
        return [n for n in rows if kind is None or n["kind"] == kind]

    def journals(self):
        with self.data.connect() as db:
            return [r[0] for r in db.execute("SELECT id FROM analysis_runs WHERE kind='position_change' ORDER BY id")]

    def sync(self, venue="hyperliquid", account=ADDRESS, start_ms=0, now_ms=None):
        return fill_journal.sync_and_notify(self.data, venue, account, start_ms=start_ms, client=self.hl,
                                            scope=HL, now_ms=now_ms)


class SupervisorRequestTests(Base):
    """AC1: one coalesced request per observed fill, after the state commit."""

    def setUp(self):
        super().setUp()
        self.g = Gateway()
        self.g.scope, self.g.account = HL.key, ADDRESS
        self.worker = Supervisor(self.store, self.g, live=True)

    def enter(self):
        row = self.store.enqueue(HL.key, plan(), live=True, now_ms=1)
        self.worker.step(row["id"], 10)
        return row["id"]

    def fill(self, pid, now, size="1"):
        self.g.size = self.g.filled = size
        self.g.orders[self.g.sent[0]["id"]]["status"] = "filled"
        return self.worker.step(pid, now)

    def test_entry_fill_records_one_request_after_state_commit(self):
        pid = self.enter()
        self.assertEqual(self.requests(), [])
        before = self.store.get(pid)
        seen = []
        original = ExecutionStore.request_journal_sync

        def spy(store, **kwargs):
            seen.append(store.get(pid)["entry_filled"])
            return original(store, **kwargs)

        with patch.object(ExecutionStore, "request_journal_sync", spy):
            self.fill(pid, 20)
        self.assertEqual(seen, ["1"])  # The committed owner already holds the fill.
        [request] = self.requests()
        self.assertEqual((request["venue"], request["account"], request["scope"]),
                         ("hyperliquid", ADDRESS, HL.key))
        self.assertEqual(request["request_count"], 1)
        # The range starts at the last committed observation before the fill.
        self.assertEqual(request["pending_since_ms"], before.get("last_observed_ms") or before["created_ms"])
        self.assertEqual(request["next_attempt_ms"], 20)

    def test_more_fills_coalesce_into_one_pending_request(self):
        pid = self.enter()
        self.fill(pid, 20)
        self.worker.step(pid, 30)  # No new fill.
        self.assertEqual(self.requests()[0]["request_count"], 1)
        self.g.size = "0.5"  # An exit or manual reduction is observed.
        self.worker.step(pid, 40)
        [request] = self.requests()
        self.assertEqual(request["request_count"], 2)

    def test_no_fill_records_no_request(self):
        self.enter()
        self.assertEqual(self.requests(), [])

    def test_paper_owner_never_requests(self):
        worker = Supervisor(self.store, self.g, live=False)
        row = self.store.enqueue(HL.key, plan(), live=False, now_ms=1)
        worker.step(row["id"], 10)
        self.assertEqual(self.requests(), [])

    def test_request_failure_leaves_supervisor_result_unchanged(self):
        def run(store, gateway, failing):
            worker = Supervisor(store, gateway, live=True)
            pid = store.enqueue(HL.key, plan(), live=True, now_ms=1)["id"]
            worker.step(pid, 10)
            gateway.size = gateway.filled = "1"
            gateway.orders[gateway.sent[0]["id"]]["status"] = "filled"
            context = (patch.object(ExecutionStore, "request_journal_sync", side_effect=sqlite3.OperationalError("locked"))
                       if failing else contextlib.nullcontext())
            with context:
                for now in (20, 30):
                    result = worker.step(pid, now)
            return result, store.attempts(pid), gateway.sent

        other = Gateway()
        other.scope, other.account = HL.key, ADDRESS
        control = run(ExecutionStore(Path(self.db.parent) / "control.sqlite"), other, False)
        with self.assertLogs("kis_hl.managed_execution", "WARNING") as logs:
            failed = run(self.store, self.g, True)

        def strip(result):
            row, attempts, sent = result
            keys = ("state", "reason", "version", "entry_filled", "observed_size", "exit_requested_ms",
                    "protective_filled", "exit_protective_filled", "first_fill_ms", "last_observed_ms")
            return ({k: row.get(k) for k in keys},
                    [(a["kind"], a["status"], a.get("quantity"), a.get("trigger_price")) for a in attempts],
                    [(s["kind"], s.get("quantity")) for s in sent])

        self.assertEqual(strip(failed), strip(control))
        self.assertIn("journal_sync_request_failed", logs.output[0])
        self.assertEqual(self.requests(), [])


class ProcessingTests(Base):
    """AC2: bounded sync, backoff retry, success clears, fallback jobs."""

    def request(self, since=T0 - 1000, now=T0):
        return fill_journal.request_sync(self.db, venue="hyperliquid", account=ADDRESS, scope=HL.key,
                                         since_ms=since, now_ms=now)

    def process(self, clock, sync=None):
        return fill_journal.process_requests(
            self.data, clock=clock,
            sync=sync or (lambda venue, account, start_ms: self.sync(venue, account, start_ms, now_ms=clock)))

    def test_success_syncs_bounded_range_clears_request_and_notifies(self):
        self.hl.fills = [hl_fill(1, "0")]
        self.request()
        self.process(T0 + 5000)
        start = self.hl.calls[0][1]
        self.assertEqual(start, T0 - 1000 - fill_journal.REQUEST_OVERLAP_MS)
        [request] = self.requests()
        self.assertIsNone(request["pending_since_ms"])
        self.assertEqual((request["last_success_ms"], request["attempts"], request["last_error"]), (T0 + 5000, 0, None))
        self.assertEqual(len(self.journals()), 1)
        [note] = self.notes("journal_batch")
        self.assertEqual(note["payload"]["entries"][0]["change"], "entry")

    def test_failure_backs_off_until_success_clears_it(self):
        self.request()
        self.hl.fail = TimeoutError("read timed out")
        self.process(T0)
        request = self.requests()[0]
        self.assertEqual((request["attempts"], request["last_error"], request["next_attempt_ms"]),
                         (1, "TimeoutError", T0 + 30_000))
        calls = len(self.hl.calls)
        self.process(T0 + 10_000)  # Not due yet.
        self.assertEqual(len(self.hl.calls), calls)
        self.process(T0 + 30_000)
        self.assertEqual(self.requests()[0]["next_attempt_ms"], T0 + 30_000 + 60_000)
        self.hl.fail = None
        self.hl.fills = [hl_fill(1, "0")]
        self.process(T0 + 90_000)
        request = self.requests()[0]
        self.assertIsNone(request["pending_since_ms"])
        self.assertEqual((request["attempts"], request["last_error"]), (0, None))

    def test_backoff_is_capped(self):
        self.assertEqual(fill_journal.backoff_ms(1), 30_000)
        self.assertEqual(fill_journal.backoff_ms(3), 120_000)
        self.assertEqual(fill_journal.backoff_ms(20), 900_000)

    def test_fill_recorded_during_sync_keeps_request_pending(self):
        self.request()

        def sync(venue, account, start_ms):
            self.request(since=T0, now=T0 + 1)  # The supervisor saw another fill meanwhile.
            return {"account_id": HL.key}

        self.process(T0 + 2, sync)
        request = self.requests()[0]
        self.assertIsNotNone(request["pending_since_ms"])
        self.assertEqual((request["next_attempt_ms"], request["last_success_ms"]), (T0 + 2, T0 + 2))

    def test_one_failing_account_does_not_block_another(self):
        self.request()
        fill_journal.request_sync(self.db, venue="kis", account="12345678-01", scope=KIS.key,
                                  since_ms=T0, now_ms=T0)

        def sync(venue, account, start_ms):
            if venue == "hyperliquid":
                raise RuntimeError("boom")
            return {"account_id": KIS.key}

        outcomes = self.process(T0, sync)
        self.assertEqual(sorted(o["status"] for o in outcomes), ["failed", "success"])

    def test_run_due_processes_requests_inside_worker_before_jobs(self):
        order = []
        configure(self.data, "job", {"kind": "account"}, 300)
        run_due(self.data, lambda config: order.append("job") or {}, clock=T0,
                before_jobs=lambda clock: order.append(("requests", clock)))
        self.assertEqual(order, [("requests", T0), "job"])

    def test_fallback_account_job_journals_unowned_fill_once(self):
        from kis_hl.data_cli import execute_job
        configure(self.data, "hl-account", {"kind": "account", "venue": "hyperliquid", "account": ADDRESS,
                                            "start_ms": 0}, 300)
        self.hl.fills = [hl_fill(1, "0")]
        with patch("kis_hl.operations_cli.scope_client", return_value=(HL, self.hl)):
            first = run_due(self.data, lambda c: execute_job(self.data, c), clock=T0)
            second = run_due(self.data, lambda c: execute_job(self.data, c), clock=T0 + 300_000)
        self.assertEqual([j["status"] for j in first["jobs"] + second["jobs"]], ["success", "success"])
        self.assertEqual(len(self.journals()), 1)
        self.assertEqual(len(self.notes("journal_batch")), 1)


class NotificationTests(Base):
    """AC3: one batch per sync, at most once per journal_id, readable messages."""

    def test_change_types_are_rendered_with_signed_quantity_price_and_kst_time(self):
        self.hl.fills = [hl_fill(1, "0"), hl_fill(2, "1"), hl_fill(3, "2", "A"),
                         hl_fill(4, "1", "A"), hl_fill(5, "0", "A"), hl_fill(6, "-1", "B", "2")]
        self.sync(now_ms=T0)
        [note] = self.notes("journal_batch")
        changes = [e["change"] for e in note["payload"]["entries"]]
        self.assertEqual(changes, ["entry", "increase", "reduction", "close", "entry", "reversal"])
        message = note["message"]
        self.assertIn("JOURNAL hyperliquid: 6 new entries", message)
        self.assertIn("hl:BTC entry +1 @ 10 USDC, 2026-10-13 22:31:05 KST", message)
        self.assertIn("reduction -1", message)
        self.assertIn("reversal +2", message)
        self.assertIn("PnL pending", message)  # HL cash coverage is never certified by routine sync.
        self.assertNotIn(ADDRESS, json.dumps(note))

    def test_close_pnl_is_confirmed_only_for_a_finalized_cycle(self):
        account = self.data.account("kis", "live", "12345678-01")
        before = fill_journal.max_run_id(self.data)
        ingest_rows(self.data, account, "statement", [statement(1, "buy", 2, 100, before=0),
                                                      statement(2, "sell", 2, 110, before=2)])
        fill_journal.ensure_baseline(self.data, account, after_run_id=before, now_ms=T0)
        pending = self.data_note(account)
        self.assertIn("PnL pending (trade_coverage_unverified)", pending["message"])
        self.data.coverage("trade", account, 0, 10**15, "complete", {})
        with self.data.connect() as db:
            db.execute("DELETE FROM journal_notified")
        confirmed = self.data_note(account, now=T0 + 1)
        close = confirmed["payload"]["entries"][-1]
        self.assertEqual((close["change"], close["pnl"]["status"]), ("close", "confirmed"))
        self.assertIn("PnL +18 KRW (+9", confirmed["message"])

    def data_note(self, account, now=T0):
        note_id = fill_journal.enqueue_journal_notifications(self.data, account, now_ms=now)
        return next(n for n in self.notes() if n["id"] == note_id)

    def test_kis_day_precision_is_labeled_without_a_time_of_day(self):
        account = self.data.account("kis", "live", "12345678-01")
        before = fill_journal.max_run_id(self.data)
        ingest_rows(self.data, account, "statement", [statement(1, "buy", 3, 70000, precision="DAY", before=0)])
        fill_journal.ensure_baseline(self.data, account, after_run_id=before, now_ms=T0)
        message = self.data_note(account)["message"]
        self.assertIn("kis:005930 entry +3 @ 70000 KRW, 2026-10-13 KST (DAY precision)", message)
        self.assertNotIn("22:31", message)

    def test_historical_journals_before_baseline_stay_silent_and_each_journal_once(self):
        self.hl.fills = [hl_fill(1, "0")]
        self.data.account("hyperliquid", "mainnet", ADDRESS)
        account = HL.key
        ingest_rows(self.data, account, "hl_fills", [hl_fill(9, "0", time=T0 - 10**9)])  # Before enablement.
        self.sync(now_ms=T0)
        [note] = self.notes("journal_batch")
        self.assertEqual(len(note["payload"]["entries"]), 1)
        self.sync(now_ms=T0 + 1)  # Same fills again.
        self.assertIsNone(fill_journal.enqueue_journal_notifications(self.data, account, now_ms=T0 + 2))
        self.assertEqual(len(self.notes("journal_batch")), 1)

    def test_concurrent_enqueue_never_notifies_a_journal_twice(self):
        account = self.data.account("hyperliquid", "mainnet", ADDRESS)
        fill_journal.ensure_baseline(self.data, account, after_run_id=0, now_ms=T0)
        ingest_rows(self.data, account, "hl_fills", [hl_fill(i, str(i - 1)) for i in range(1, 6)])
        barrier = threading.Barrier(4)

        def worker():
            barrier.wait()
            fill_journal.enqueue_journal_notifications(DataStore(self.db), account, now_ms=T0)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        ids = [e["journal_id"] for n in self.notes("journal_batch") for e in n["payload"]["entries"]]
        self.assertEqual(sorted(ids), self.journals())

    def test_large_batch_lists_twenty_entries_and_counts_the_rest(self):
        account = self.data.account("hyperliquid", "mainnet", ADDRESS)
        fill_journal.ensure_baseline(self.data, account, after_run_id=0, now_ms=T0)
        ingest_rows(self.data, account, "hl_fills", [hl_fill(i, str(i - 1)) for i in range(1, 26)])
        note = self.data_note(account)
        self.assertEqual(len(note["payload"]["entries"]), 20)
        self.assertEqual(note["payload"]["more"], 5)
        self.assertIn("... and 5 more", note["message"])

    def test_unknown_notification_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            notification_message({"kind": "surprise", "position_id": "x", "payload": {}})

    def test_hermes_lists_and_acknowledges_journal_batches_through_existing_cli(self):
        self.hl.fills = [hl_fill(1, "0")]
        self.sync(now_ms=T0)
        code, listed, _ = cli(self.db, "supervisor", "notifications", "--venue", "hyperliquid")
        self.assertEqual(code, 0)
        [note] = listed["notifications"]
        self.assertEqual(note["kind"], "journal_batch")
        self.assertIn("JOURNAL hyperliquid: 1 new entry", note["message"])
        self.assertNotIn(ADDRESS, json.dumps(listed))
        code, result, _ = cli(self.db, "supervisor", "notification-result", "--venue", "hyperliquid",
                              "--notification-id", str(note["id"]), "--result", "delivered")
        self.assertEqual((code, result["delivery_attempts"]), (0, 1))
        self.assertEqual(cli(self.db, "supervisor", "notifications", "--venue", "hyperliquid")[1]["notifications"], [])


def cli(db, *args, scope=HL):
    from kis_hl.cli import main
    out, err = io.StringIO(), io.StringIO()
    with (patch("kis_hl.cli.load_env_file"),
          patch("kis_hl.operations_cli.scope_client", return_value=(scope, None)),
          contextlib.redirect_stdout(out), contextlib.redirect_stderr(err)):
        code = main(["--db", str(db), *args])
    return code, (json.loads(out.getvalue()) if out.getvalue() else None), err.getvalue()


class StatusTests(Base):
    """AC4: read-only status and once-per-day summary.

    Facts are known at real ingestion time, so this fixture is anchored to the clock."""

    def setUp(self):
        super().setUp()
        now = fill_journal.current_ms() - 1000
        self.hl.fills = [hl_fill(1, "0", time=now - 3 * 86_400_000), hl_fill(2, "1", "A", time=now - 2 * 86_400_000),
                         hl_fill(3, "0", time=now)]
        self.sync(now_ms=now)
        kis = self.data.account("kis", "live", "12345678-01")
        ingest_rows(self.data, kis, "statement", [statement(1, "buy", 2, 100, before=0, at=now - 86_400_000),
                                                  statement(2, "sell", 2, 110, before=2, at=now - 80_000_000)])
        self.data.coverage("trade", kis, 0, 10**15, "complete", {})
        fill_journal.request_sync(self.db, venue="hyperliquid", account=ADDRESS, scope=HL.key,
                                  since_ms=now, now_ms=now)
        with self.data.connect() as db:
            db.execute("UPDATE journal_sync_requests SET attempts=2,last_error='TimeoutError'")
        configure(self.data, "hl-account", {"kind": "account", "venue": "hyperliquid", "account": ADDRESS,
                                            "start_ms": 0}, 300)
        self.kis = kis

    def status(self, *extra):
        code, result, err = cli(self.db, "data", "journal-status", *extra)
        self.assertEqual(code, 0, err)
        return result

    def test_status_reports_required_fields_for_hl_and_kis_without_writing(self):
        before = (self.db.read_bytes(), self.db.stat().st_mtime_ns)
        wal = self.db.with_name(self.db.name + "-wal")
        wal_before = wal.read_bytes() if wal.exists() else b""
        result = self.status()
        self.assertEqual((self.db.read_bytes(), self.db.stat().st_mtime_ns), before)
        self.assertEqual(wal.read_bytes() if wal.exists() else b"", wal_before)
        accounts = {a["venue"]: a for a in result["accounts"]}
        hl, kis = accounts["hyperliquid"], accounts["kis"]
        self.assertEqual([p["instrument"] for p in hl["open_positions"]], ["hl:BTC"])
        self.assertEqual(hl["open_positions"][0]["quantity"], "1")
        self.assertEqual([e["change"] for e in hl["today"]], ["entry"])
        self.assertEqual(hl["cycles"]["closed"], 1)
        nine = {"trade_count", "win_rate_pct", "average_profit", "average_loss", "success_failure_ratio",
                "adjusted_success_failure_ratio", "max_profit", "max_loss", "average_profit_holding_days"}
        self.assertLessEqual(nine, set(hl["cycles"]["statistics"]))
        self.assertEqual(hl["cycles"]["statistics"]["trade_count"], 0)  # Pending, never fabricated.
        self.assertIn("cash_coverage_unverified", hl["pending"]["reasons"])
        self.assertEqual(kis["cycles"]["statistics"]["trade_count"], 1)
        sync = hl["sync"]
        self.assertEqual((sync["request"]["attempts"], sync["request"]["last_error"]), (2, "TimeoutError"))
        self.assertEqual(sync["jobs"][0]["id"], "hl-account")
        self.assertIn("worker_last_seen_ms", result)
        self.assertNotIn(ADDRESS, json.dumps(result))

    def test_summary_is_enqueued_once_per_kst_date_from_the_same_status(self):
        first = self.status("--enqueue-summary")
        self.assertEqual(len(first["enqueued"]), 2)
        self.status("--enqueue-summary")
        daily = self.notes("journal_daily")
        self.assertEqual(len(daily), 2)
        hl = next(n for n in daily if n["payload"]["venue"] == "hyperliquid")
        self.assertIn(f"DAILY JOURNAL {first['kst_date']}", hl["message"])
        self.assertIn("open hl:BTC long 1", hl["message"])
        self.assertIn("sync request pending, 2 failed attempts (TimeoutError)", hl["message"])

    def test_uninitialized_database_fails_without_creating_it(self):
        missing = self.db.parent / "missing.sqlite"
        code, _, err = cli(missing, "data", "journal-status")
        self.assertNotEqual(code, 0)
        self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
