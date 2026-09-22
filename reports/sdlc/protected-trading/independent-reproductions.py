"""Offline independent regressions: real CLI/locks and late fill attribution.

No vendor request can be reached: the scheduler is seeded three hours ahead and
the lock probe uses the local lock directly. All databases use temporary paths.
Run from the repository root with python3 -B.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from kis_hl.execution_lock import account_lock
from kis_hl.journal_history import attribute_fill
from kis_hl.journal_sync import Fill, JournalLedger, Scope, SyncSchedule
from kis_hl.managed_execution import ExecutionStore
from tests.test_managed_execution import plan


def scheduler_probe(folder):
    account = "0x" + "1" * 40
    scope = Scope("hyperliquid", "testnet", account)
    database = folder / "scheduler.sqlite"
    ledger = JournalLedger(database)
    SyncSchedule(ledger, scope).success(int(time.time() * 1000))
    env = {
        "PATH": os.environ["PATH"],
        "PYTHONPATH": str(ROOT),
        "PYTHONDONTWRITEBYTECODE": "1",
        "HYPERLIQUID_WALLETADDRESS": account,
        "HYPERLIQUID_PRIVATEKEY": "",
        "HYPERLIQUID_BASE_URL": "https://api.hyperliquid-testnet.xyz",
        "HYPERLIQUID_KEY_PROFILE": "default",
    }
    command = [
        sys.executable, "-B", "-m", "kis_hl.cli", "--db", str(database),
        "journal", "run", "--venue", "hyperliquid", "--account", account,
        "--start-ms", "0", "--poll-seconds", "1",
    ]
    child = subprocess.Popen(
        command, cwd=folder, env=env, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True,
    )
    try:
        # Wait for the actual process to initialize. The future due time means it
        # cannot collect history during this bounded observation.
        time.sleep(0.8)
        if child.poll() is not None:
            raise RuntimeError("Scheduler stopped unexpectedly: " + str(child.communicate()))
        unavailable = 0
        for _ in range(10):
            try:
                with account_lock("journal:testnet", scope.key):
                    pass
            except RuntimeError:
                unavailable += 1
            time.sleep(0.02)
        return {
            "scenario": "IV-1-idle-scheduler",
            "local_lock_probes": 10,
            "unavailable_probes": unavailable,
            "passed": unavailable == 0,
        }
    finally:
        child.terminate()
        child.communicate(timeout=5)


def attribution_probe(folder):
    database = folder / "attribution.sqlite"
    ledger = JournalLedger(database)
    scope = Scope("hyperliquid", "mainnet", "offline-fixture")
    fill = Fill(
        "execution-1", "BTC", 10, "buy", "1", "100", "USDC", fee="0",
        order_id="42", position_before="0",
    )
    coverage = dict(
        start_ms=0, end_ms=100, source="offline automatic-history fixture",
        complete=True, costs_complete=True,
    )
    ledger.ingest(scope, [attribute_fill(ledger, scope, fill)], **coverage)
    execution = ExecutionStore(database)
    position = execution.enqueue(scope.key, plan(), live=True, now_ms=1)
    attempt = execution.attempt(position, "entry", 9, quantity="1", price="100")
    execution.update_attempt(attempt, status="SUBMITTED", order_id="42")
    # Only local evidence is constructed; no supervisor or venue client is called.
    try:
        ledger.ingest(scope, [attribute_fill(ledger, scope, fill)], **coverage)
    except ValueError as exc:
        return {"scenario": "IV-2-late-attribution", "passed": False, "error": str(exc)}
    return {"scenario": "IV-2-late-attribution", "passed": True}


def main():
    with tempfile.TemporaryDirectory(prefix="protected-independent-") as temporary:
        folder = Path(temporary)
        results = [scheduler_probe(folder), attribution_probe(folder)]
    print(json.dumps({"results": results, "vendor_calls": 0}, indent=2))
    return 0 if all(result["passed"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
