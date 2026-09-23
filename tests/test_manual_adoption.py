"""Native defaults and explicit manual-position ownership; no exchange network."""
import contextlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from kis_hl.cli import main
from kis_hl.managed_execution import ExecutionStore, Supervisor, validate_plan
from tests.test_managed_execution import Gateway, plan
from tests import test_managed_gateways


class ManualAdoptionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name)/"state.sqlite"
        self.store = ExecutionStore(self.path)
        self.g, self.info, _, _, entry = test_managed_gateways.ManagedGatewayTests().hl()
        self.g.trading.verification_db_path = self.path
        entry["timestamp"] = 9
        stop = dict(oid=43, coin="BTC", side="A", reduceOnly=True, isTrigger=True,
                    orderType="Stop Market", sz="1", triggerPx="96")
        self.orders = {42: {"status": "filled", "order": entry},
                       43: {"status": "open", "order": stop}}
        self.info.order_status.side_effect = lambda *, oid: {"status": "order", "order": self.orders[int(oid)]}
        self.info.frontend_open_orders.side_effect = lambda **kw: [r["order"] for r in self.orders.values() if r["status"] == "open"]
        self.fills = self.info.user_fills_by_time.return_value
        self.fills[0]["startPosition"] = "0"
        self.info.user_fills.return_value = self.fills
        self.g.preflight = Mock(return_value=Gateway().preflight(plan(), 20) | {
            "position": "1", "open_orders": [stop], "trailing_price_step": "0.0001"})
        self.worker = Supervisor(self.store, self.g, live=True)
        def trail(**kw):
            self.orders[44] = {"status": "open", "order": dict(oid=44, coin="BTC", side="A",
                sz="1", reduceOnly=True, isTrigger=True, orderType="Trailing Stop Market",
                triggerCondition="retracement 4, best waiting")}
            return SimpleNamespace(status="submitted", response={"response":{"data":{"statuses":[{"resting":{"oid":44}}]}}})
        self.g.trading.place_trailing_stop_order.side_effect = trail

    def queue(self, *, live=True, **changes):
        p=plan(); p.pop("trailing_provider", None); p.update(changes)
        return self.store.enqueue_adoption(self.g.scope, p, entry_order_id=42, stop_order_id=43, live=live, now_ms=20)

    def step(self, row, now=21):
        self.info.l2_book.return_value["time"] = now
        with patch("kis_hl.managed_gateways.time.time", return_value=now/1000):
            return self.worker.step(row["id"], now)

    def test_new_hl_defaults_native_kis_and_explicit_local_stay_local(self):
        p=plan(); p.pop("trailing_provider", None)
        self.assertEqual(validate_plan(p, 1)["trailing_provider"], "native")
        self.assertEqual(validate_plan(p | {"trailing_provider":"local"}, 1)["trailing_provider"], "local")
        self.assertEqual(validate_plan(p | {"instrument":"kis:SPY", "verified_price_step":"0.01"}, 1)["trailing_provider"], "local")

    def test_paper_adoption_has_no_exchange_reads_or_attempts(self):
        row=self.queue(live=False)
        g=SimpleNamespace(scope=self.g.scope, network="offline", account="offline")
        result=Supervisor(self.store,g).step(row["id"],21)
        self.assertEqual(result["state"],"PREVIEWED")
        self.assertEqual(self.store.attempts(row["id"]),[])

    def test_adoption_imports_atomically_then_submits_only_one_native_trail(self):
        row=self.queue()
        self.assertEqual(row["state"],"ADOPTING")
        result=self.step(row)
        self.assertEqual(result["state"],"PROTECTING")
        self.assertEqual(result["created_ms"],20)
        self.assertEqual(result["fill_history_start_ms"],9)
        self.assertEqual(result["first_fill_ms"],10)
        self.assertEqual(result["native_trailing_distance"],"4")
        self.assertEqual([a["order_id"] for a in self.store.attempts(row["id"])],["42","43"])
        self.g.trading.place_order.assert_not_called()
        self.g.trading.place_trailing_stop_order.assert_not_called()
        self.step(row,22); self.step(row,23)
        self.worker=Supervisor(self.store,self.g,live=True)
        self.step(row,24)
        self.g.trading.place_trailing_stop_order.assert_called_once()
        self.g.trading.place_order.assert_not_called()
        self.assertEqual(self.orders[43]["status"],"open")

    def test_bad_evidence_never_imports_or_sends_orders(self):
        changes=[lambda:self.orders[42].update(status="open"),
            lambda:self.orders[42]["order"].update(oid=99),
            lambda:self.orders[43]["order"].update(reduceOnly=False),
            lambda:self.orders[43]["order"].update(sz="0.5"),
            lambda:self.orders[43]["order"].update(triggerPx="90"),
            lambda:self.fills[0].update(startPosition="-1"),
            lambda:self.fills[0].update(px="101"),
            lambda:self.info.user_fills.configure_mock(return_value=[{"time":11}])]
        # A distinct fixture/database for each rejecting condition.
        for change_index in range(len(changes)):
            with self.subTest(change_index=change_index):
                if change_index: self.setUp()
                changes[change_index]()
                row=self.queue();result=self.step(row)
                self.assertEqual(result["state"],"INTERVENTION")
                self.assertEqual(self.store.attempts(row["id"]),[])
                self.g.trading.place_order.assert_not_called()
                self.g.trading.place_trailing_stop_order.assert_not_called()

    def test_failed_adoption_recovery_and_cancel_never_become_entry(self):
        row=self.queue();self.orders[43]["status"]="canceled"
        self.assertEqual(self.step(row)["state"],"INTERVENTION")
        with patch("kis_hl.cli.load_env_file"),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--db",str(self.path),"order","recover","--id",row["id"]]),0)
        self.assertEqual(self.store.get(row["id"])["state"],"ADOPTING")
        self.store.request_exit(row["id"],22,cancel_only=True)
        self.assertEqual(self.step(row,23)["state"],"CLOSED")
        self.g.trading.place_order.assert_not_called()

    def test_import_rollback_and_reused_native_id_rejected(self):
        row=self.queue()
        with self.store.connect() as db:
            db.execute("CREATE TRIGGER fail_import BEFORE INSERT ON managed_attempts WHEN NEW.kind='stop' BEGIN SELECT RAISE(ABORT,'fixture crash'); END")
        with self.assertRaises(sqlite3.IntegrityError): self.step(row)
        self.assertEqual(self.store.attempts(row["id"]),[])
        self.assertEqual(self.store.get(row["id"])["state"],"ADOPTING")
        with self.store.connect() as db: db.execute("DROP TRIGGER fail_import")
        self.step(row)
        original=self.store.get(row["id"]);original["state"]="CLOSED";self.store.save(original)
        second=self.queue(intent_id="second")
        self.assertEqual(self.step(second)["state"],"INTERVENTION")
        self.assertEqual(self.store.attempts(second["id"]),[])

    def test_legacy_owner_rejected_even_if_worker_stopped(self):
        from kis_hl.trailing_storage import TrailStore
        TrailStore(self.path).enroll(dict(network=self.g.network.rstrip('/'),account=self.g.account.lower(),
                                        coin="BTC",mode="live",state="PROTECTED"))
        row=self.queue()
        self.assertEqual(self.step(row)["state"],"INTERVENTION")
        self.assertEqual(self.store.attempts(row["id"]),[])

    def test_imported_order_does_not_relabel_manual_fill_as_agent(self):
        from kis_hl.journal_history import attribute_fill
        from kis_hl.journal_sync import Fill, JournalLedger, Scope
        row=self.queue();self.step(row)
        fill=Fill("manual","BTC",30,"sell","1","96","USDC",order_id="43",origin="web")
        result=attribute_fill(JournalLedger(self.path),Scope("hyperliquid","testnet","fixture"),fill)
        self.assertEqual(result.origin,"web")
        self.assertEqual(result.strategy,"unassigned")

    def test_cli_queues_explicit_harness_handoff_without_live_io(self):
        p=plan(harness="hermes");p.pop("trailing_provider",None)
        p["expires_ms"]=9999999999999
        source=self.path.parent/"plan.json";source.write_text(json.dumps(p))
        from kis_hl.journal_sync import Scope
        out=io.StringIO()
        with patch("kis_hl.cli.load_env_file"),patch("kis_hl.operations_cli.scope_client",return_value=(Scope("hyperliquid","testnet","fixture"),None)),contextlib.redirect_stdout(out):
            code=main(["--db",str(self.path),"order","adopt","--input",str(source),"--entry-order-id","42","--stop-order-id","43"])
        self.assertEqual(code,0)
        row=json.loads(out.getvalue());self.assertEqual(row["mode"],"paper")
        self.assertEqual(row["state"],"ADOPTING")
        self.assertEqual(row["plan"]["harness"],"hermes")



class ConcurrentBackupTests(unittest.TestCase):
    def fixture(self):
        from tests.test_native_trailing import NativeTrailingManagedTests
        case=NativeTrailingManagedTests();case.setUp();self.addCleanup(case.doCleanups)
        row=case.start()
        case.g.orders[case.g.sent[-1]["id"]].update(active=False,retracement="4",retracement_unit="quote")
        snapshot=case.g.snapshot
        case.g.snapshot=lambda *a:snapshot(*a) | {"price":"95"}
        return case,row

    def test_local_backup_exits_while_native_waits_and_retains_exchange_protection(self):
        c,row=self.fixture()
        result=c.worker.step(row["id"],5)
        self.assertIsNotNone(result["exit_requested_ms"])
        self.assertEqual([a["kind"] for a in c.g.sent],["entry","stop","trailing","exit"])
        self.assertEqual(c.g.orders[c.g.sent[1]["id"]]["status"],"open")
        self.assertEqual(c.g.orders[c.g.sent[2]["id"]]["status"],"open")
        c.worker=Supervisor(c.store,c.g,live=True);c.worker.step(row["id"],6)
        self.assertEqual(len([a for a in c.g.sent if a["kind"]=="exit"]),1)

    def test_historical_native_without_backup_field_keeps_prior_policy(self):
        c,row=self.fixture()
        saved=c.store.get(row["id"]);saved["plan"].pop("local_trailing_backup",None);c.store.save(saved)
        result=c.worker.step(row["id"],5)
        self.assertIsNone(result["exit_requested_ms"])
        self.assertEqual(len(c.g.sent),3)

    def test_local_backup_keeps_monitoring_native_condition_intervention(self):
        c,row=self.fixture()
        c.g.orders[c.g.sent[2]["id"]]["trailing_readback_error"]="unrecognized format"
        result=c.worker.step(row["id"],5)
        self.assertIsNotNone(result["exit_requested_ms"])
        self.assertEqual(c.g.sent[-1]["kind"],"exit")
