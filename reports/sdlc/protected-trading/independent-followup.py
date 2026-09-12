"""Candidate follow-up using real locks/storage/adapters and offline history."""

import importlib.util
import json
from pathlib import Path
import tempfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("prior", HERE / "independent-reproductions.py")
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)

from kis_hl.journal_history import sync_hyperliquid


def adapter_probe(folder):
    ledger = prior.JournalLedger(folder / "adapter.sqlite")
    scope = prior.Scope("hyperliquid", "mainnet", "offline-fixture")

    class OfflineHistory:
        row = dict(tid="execution-1", coin="BTC", time=10, side="B", sz="1",
                   px="100", fee="0", feeToken="USDC", oid=42, startPosition="0")

        def user_fills_by_time(self, **kwargs):
            return [dict(self.row)]

        def user_fills(self):
            return [dict(self.row)]

        def user_funding(self, **kwargs):
            return []

    info = OfflineHistory()
    sync = lambda: sync_hyperliquid(ledger, scope, info, start_ms=10, end_ms=100)
    sync()
    execution = prior.ExecutionStore(ledger.path)
    position = execution.enqueue(scope.key, prior.plan(), live=True, now_ms=1)
    attempt = execution.attempt(position, "entry", 9, quantity="1", price="100")
    execution.update_attempt(attempt, status="SUBMITTED", order_id="42")
    sync()
    sync()
    with ledger.connect() as db:
        rows = db.execute("SELECT revision,payload FROM journal_source_fills ORDER BY revision").fetchall()
    assert len(rows) == 2, "Enrichment must create exactly one revision"
    before, after = (json.loads(row["payload"]) for row in rows)
    assert before["strategy"] == "unassigned"
    assert after["strategy"] != "unassigned" and after["origin"] == "agent"
    attribution = {"strategy", "origin", "strategy_version", "harness", "signal_id"}
    assert all(before[k] == after[k] for k in before.keys() - attribution)
    info.row["px"] = "101"
    try:
        sync()
    except ValueError as error:
        assert "explicit correction" in str(error)
    else:
        raise AssertionError("Automatic economic correction was accepted")
    with ledger.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM journal_source_fills").fetchone()[0] == 2
    return dict(scenario="IV-2-real-history-adapter", revisions=2,
                idempotent_replay=True, economic_change_rejected=True, passed=True)


with tempfile.TemporaryDirectory(prefix="protected-followup-") as temporary:
    folder = Path(temporary)
    results = [prior.scheduler_probe(folder), adapter_probe(folder)]
print(json.dumps(dict(results=results, vendor_calls=0), indent=2))
raise SystemExit(0 if all(result["passed"] for result in results) else 1)
